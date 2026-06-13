"""BLOC 3 Portfolio — Structure de corrélation (.txt §4 HRP + conv "dendrogramme = interface
de validation, remplace pré-mortem bouton OK"). Couvre points 32-37 :
  - Matrice de corrélation entre holdings (heatmap)
  - Dendrogramme HRP : nœuds=holdings, taille=poids, couleur=secteur GICS
  - Beta agrégé par cluster
  - Assets ponts (si retiré → 2 groupes indépendants)
  - Poids actuels vs poids HRP suggérés
  - Variante HERC (Equal Risk Contribution)

HRP implémenté from scratch (scipy.cluster.hierarchy) — pas de dépendance riskfolio-lib.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, dendrogram as scipy_dendro
from scipy.spatial.distance import squareform


def _corr_matrix(returns: pd.DataFrame) -> pd.DataFrame:
    return returns.corr()


def _distance_matrix(corr: pd.DataFrame) -> pd.DataFrame:
    """Distance de Mantegna : D(i,j) = sqrt(0.5 × (1 − ρ)). (.txt §4 HRP étape 1)"""
    d = np.sqrt(0.5 * (1 - corr.clip(-1, 1)))
    d_vals = d.values.copy()
    np.fill_diagonal(d_vals, 0.0)
    return pd.DataFrame(d_vals, index=d.index, columns=d.columns)


def correlation_heatmap(returns: pd.DataFrame) -> dict:
    """Point 32 — matrice corrélation entre holdings pour heatmap front."""
    corr = _corr_matrix(returns)
    return {"tickers": corr.columns.tolist(),
            "matrix": corr.round(4).values.tolist()}


def _quasi_diag(linkage_matrix: np.ndarray) -> list[int]:
    """Quasi-diagonalisation Lopez de Prado : ordonne les indices selon le clustering."""
    link = linkage_matrix.astype(int)
    n_items = link[-1, 3]  # total observations
    sort_ix = [link[-1, 0], link[-1, 1]]
    num_items = link[-1, 3]
    while max(sort_ix) >= n_items:
        new = []
        for i in sort_ix:
            if i < n_items:
                new.append(i)
                continue
            row = link[i - n_items]
            new.append(int(row[0]))
            new.append(int(row[1]))
        sort_ix = new
    return [int(i) for i in sort_ix]


def _rec_bipart(cov: pd.DataFrame, sort_ix: list[int]) -> pd.Series:
    """Recursive bisection — alloue inverse-variance dans chaque sous-cluster."""
    w = pd.Series(1.0, index=[cov.columns[i] for i in sort_ix])
    clusters = [list(range(len(sort_ix)))]
    while clusters:
        next_clusters = []
        for cluster in clusters:
            if len(cluster) <= 1:
                continue
            half = len(cluster) // 2
            left, right = cluster[:half], cluster[half:]

            def _cluster_var(idxs):
                sub_cov = cov.iloc[[sort_ix[i] for i in idxs], [sort_ix[i] for i in idxs]]
                inv_diag = 1.0 / np.diag(sub_cov)
                w_ = inv_diag / inv_diag.sum()
                return float(w_ @ sub_cov.values @ w_)

            v_left, v_right = _cluster_var(left), _cluster_var(right)
            alpha = 1 - v_left / (v_left + v_right) if (v_left + v_right) else 0.5
            for i in left:
                w.iloc[i] *= alpha
            for i in right:
                w.iloc[i] *= (1 - alpha)
            next_clusters.extend([left, right])
        clusters = next_clusters
    return w


def hrp_weights(returns: pd.DataFrame) -> pd.Series:
    """HRP Lopez de Prado 2016 — distance Mantegna + Ward + inverse-variance récursif.
    Output : pd.Series tickers → poids HRP suggérés (.txt §4 — 'SAINHE suggère, ne force pas')."""
    cov = returns.cov()
    corr = returns.corr()
    dist = _distance_matrix(corr)
    link = linkage(squareform(dist.values, checks=False), method="ward")
    sort_ix = _quasi_diag(link)
    w = _rec_bipart(cov, sort_ix)
    return w.reindex(returns.columns).fillna(0.0)


def herc_weights(returns: pd.DataFrame) -> pd.Series:
    """Variante HERC : Equal Risk Contribution dans chaque cluster au lieu d'inverse-variance.
    Implémentation simplifiée : on remplace l'inverse-variance par ERC dans la bisection."""
    cov = returns.cov()
    corr = returns.corr()
    dist = _distance_matrix(corr)
    link = linkage(squareform(dist.values, checks=False), method="ward")
    sort_ix = _quasi_diag(link)

    # ERC dans cluster : poids ∝ 1/σ (proxy ERC pour le cas multivarié c'est itératif ; on
    # garde la version Bruder-Roncalli simplifiée)
    w = pd.Series(1.0, index=[cov.columns[i] for i in sort_ix])
    clusters = [list(range(len(sort_ix)))]
    while clusters:
        next_clusters = []
        for cluster in clusters:
            if len(cluster) <= 1:
                continue
            half = len(cluster) // 2
            left, right = cluster[:half], cluster[half:]

            def _cluster_vol(idxs):
                sub_cov = cov.iloc[[sort_ix[i] for i in idxs], [sort_ix[i] for i in idxs]]
                inv_sigma = 1.0 / np.sqrt(np.diag(sub_cov))
                w_ = inv_sigma / inv_sigma.sum()
                return float(np.sqrt(w_ @ sub_cov.values @ w_))

            vl, vr = _cluster_vol(left), _cluster_vol(right)
            alpha = vr / (vl + vr) if (vl + vr) else 0.5
            for i in left:
                w.iloc[i] *= alpha
            for i in right:
                w.iloc[i] *= (1 - alpha)
            next_clusters.extend([left, right])
        clusters = next_clusters
    return w.reindex(returns.columns).fillna(0.0)


def dendrogram_data(returns: pd.DataFrame, weights: dict[str, float],
                     sector_map: dict[str, str] | None = None) -> dict:
    """Données dendrogramme pour le front (.txt §4 — interface de validation visuelle).
    Format prêt à consommer : pour chaque ticker, position dans le cluster + groupe."""
    corr = _corr_matrix(returns)
    dist = _distance_matrix(corr)
    link = linkage(squareform(dist.values, checks=False), method="ward")
    # On utilise scipy pour obtenir leaves + structure de fusion
    dendro = scipy_dendro(link, labels=returns.columns.tolist(), no_plot=True)
    return {
        "linkage": link.tolist(),
        "leaves_order": dendro["ivl"],
        "leaves_color_list": dendro.get("leaves_color_list", []),
        "nodes": [{"ticker": t, "weight": weights.get(t, 0.0),
                   "sector": (sector_map or {}).get(t, "Unknown")}
                  for t in dendro["ivl"]],
    }


def cluster_assignments(returns: pd.DataFrame, n_clusters: int = 4) -> dict[str, int]:
    """Affecte chaque ticker à un cluster (pour cluster beta + table croisement)."""
    from scipy.cluster.hierarchy import fcluster
    corr = _corr_matrix(returns)
    dist = _distance_matrix(corr)
    link = linkage(squareform(dist.values, checks=False), method="ward")
    labels = fcluster(link, t=n_clusters, criterion="maxclust")
    return {t: int(c) for t, c in zip(returns.columns, labels)}


def cluster_beta_aggregation(weights: dict[str, float], betas: dict[str, float],
                              clusters: dict[str, int]) -> dict[int, dict]:
    """Σ(w_i × β_i) par cluster (.txt point 34 — révèle quel cluster drive le risque marché)."""
    by_cluster: dict[int, dict] = {}
    for t, c in clusters.items():
        if t not in weights or t not in betas:
            continue
        agg = by_cluster.setdefault(c, {"members": [], "aggregated_beta": 0.0,
                                         "total_weight": 0.0})
        agg["members"].append(t)
        agg["aggregated_beta"] += weights[t] * betas[t]
        agg["total_weight"] += weights[t]
    return by_cluster


def bridge_assets(returns: pd.DataFrame, weights: dict[str, float]) -> list[dict]:
    """Asset pont : si retiré, augmentation matérielle de la 'distance moyenne entre clusters'.
    Heuristique simple (.txt point 35) : pour chaque ticker, mesurer la corrélation moyenne
    aux autres clusters ; les ponts ont une corrélation cross-cluster élevée."""
    clusters = cluster_assignments(returns)
    corr = _corr_matrix(returns).abs()
    bridges = []
    for t, c in clusters.items():
        other_cluster_tickers = [u for u, cu in clusters.items() if cu != c]
        if not other_cluster_tickers:
            continue
        cross = corr.loc[t, other_cluster_tickers].mean()
        bridges.append({"ticker": t, "cluster": c,
                         "avg_cross_cluster_corr": float(cross),
                         "weight": weights.get(t, 0.0)})
    return sorted(bridges, key=lambda b: b["avg_cross_cluster_corr"], reverse=True)[:5]


def compare_weights(current: dict[str, float], hrp: pd.Series) -> list[dict]:
    """Poids actuels user vs poids HRP suggérés côte à côte (.txt point 36 — actionnable)."""
    out = []
    for t in set(current) | set(hrp.index):
        cw, sw = current.get(t, 0.0), float(hrp.get(t, 0.0))
        out.append({"ticker": t, "current_weight": cw, "hrp_suggested": sw,
                    "delta": cw - sw,
                    "flag_concentration": (cw - sw) > 0.05})
    return sorted(out, key=lambda x: abs(x["delta"]), reverse=True)
