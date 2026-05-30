# -*- coding: utf-8 -*-
"""
Can oil market volatility predict U.S. financial market volatility
through instantaneous comovement?

Financial Econometrics — semester project (group 3).
Daily FRED data (2010+), OLS with HAC standard errors, interaction and
quadratic terms, and a PE test for the log-linear specification.

Requirements:
    pip install fredapi pandas statsmodels matplotlib seaborn numpy

Usage:
    export FRED_API_KEY=your_free_key   # https://fred.stlouisfed.org/docs/api/api_key.html
    python oil_vix_volatility.py
"""

import os

import pandas as pd
from fredapi import Fred

# 1) Connect — key read from environment (never hard-code secrets)
fred = Fred(api_key=os.environ["FRED_API_KEY"])

# 2) Define MANY series (safe IDs only)
series = {
    # --- Oil / Energy ---
    "OVXCLS":        "OilVol_OVX",            # CBOE Crude Oil Volatility (implied)
    "DCOILWTICO":    "Oil_WTI_Spot",          # WTI spot price 0
    "DCOILBRENTEU":  "Oil_Brent_Spot",        # Brent spot price 0

    # --- Market Volatility / Equity Indexes ---
    "VIXCLS":        "MktVol_VIX",            # S&P 500 implied vol 0
    "VXOCLS":        "MktVol_VXO",            # S&P 100 implied vol 0
    "SP500":         "SP500_Index",           # S&P 500 price 0
    "NASDAQCOM":     "NASDAQ_Index",          # Nasdaq Composite 0

    # --- Financial Stress / Conditions ---
    "STLFSI4":       "Stress_STLFSI",         # St. Louis Financial Stress (latest version) 1
    "NFCI":          "Cond_NFCI",             # Chicago Fed NFCI 0
    "ANFCI":         "Cond_ANFCI",            # Adjusted NFCI 0

    # --- Credit risk / Spreads ---
    "BAMLH0A0HYM2":  "Spread_HY_OAS",         # ICE BofA US High Yield OAS 0
    "BAMLC0A0CM":    "Spread_US_Corp_OAS",    # ICE BofA US Corporate OAS (broad) 1  <-- NEW
    "DBAA":          "Yield_BAA",             # Moody's BAA corp yield 0
    "DAAA":          "Yield_AAA",             # Moody's AAA corp yield 0
    "TEDRATE":       "Spread_TED",            # TED spread 1
    "AAAFF":         "Spread_AAA_FF",         # Aaa minus Fed Funds 0              <-- NEW
    "BAAFF":         "Spread_BAA_FF",         # Baa minus Fed Funds  0             <-- NEW

    # --- Term structure / Treasury ---
    "DGS10":         "Yield_US10Y",           # 10-year Treasury 0
    "DGS2":          "Yield_US2Y",            # 2-year Treasury 0
    "DGS3MO":        "Yield_US3M",            # 3-month T-bill 0
    "T10Y2Y":        "Spread_10Y_2Y",         # 10y-2y term spread 0
    "T10Y3M":        "Spread_10Y_3M",         # 10y-3m term spread 0

    # --- Macro controls ---
    "CPIAUCSL":      "CPI_AllItems",          # CPI (index) 1
    "PCEPI":         "PCE_Price_Index",       # PCE price index 1
    "UNRATE":        "Unemployment_Rate",     # Unemployment % 1
    "INDPRO":        "Industrial_Production", # Industrial production 1
    "USREC":         "NBER_Recession_Flag",   # Recession dummy (monthly) 0
    "RECPROUSM156N": "Recession_Prob_Smoothed", # Smoothed U.S. Recession Prob. 1  <-- NEW

    # --- FX / Dollar ---
    "DEXUSEU":       "FX_USD_EUR",            # USD/EUR 1
    "DTWEXBGS":      "Dollar_Broad_Index",    # Trade-weighted USD 1 (broad, goods)

    # --- Liquidity / Balance sheet ---
    "WALCL":         "Fed_Total_Assets",      # Fed balance sheet 0 (H.4.1)

    # --- Uncertainty / Commodities (controls) ---
    "USEPUINDXD":    "Uncertainty_EPU_US",    # Economic Policy Uncertainty (US) 1  <-- NEW
    "PCOPPUSDM":     "Copper_Price_Global"    # Global price of Copper (IMF) 0     <-- NEW
}

# 3) Download with per-series error handling
raw = {}
for sid, nice in series.items():
    try:
        s = fred.get_series(sid)
        s.name = nice
        raw[nice] = s
        print(f"✓ {sid:>12}  →  {nice}")
    except Exception as e:
        print(f"× {sid:>12}  (skipped)  — {e}")

# 4) Combine to one DataFrame (raw, mixed frequencies)
df = pd.DataFrame(raw)

df_recent = df[df.index >= '2010-01-01'].copy()   # .copy() avoids SettingWithCopyWarning below

"""# Vérification des NA"""

print((df_recent.notna().sum() / len(df_recent)) * 100)

"""# Remplissage des données mensuelles ou hebdomadaires"""

cols_to_fill = ['Stress_STLFSI','Cond_NFCI','Cond_ANFCI','CPI_AllItems','PCE_Price_Index','Unemployment_Rate','Industrial_Production','NBER_Recession_Flag','Fed_Total_Assets','Copper_Price_Global','Recession_Prob_Smoothed',]  # les colonnes que tu veux remplir
df_recent[cols_to_fill] = df_recent[cols_to_fill].ffill()

print((df_recent.notna().sum() / len(df_recent)) * 100)

"""# Clean dataset"""

df_recent = df_recent.dropna()
print((df_recent.notna().sum() / len(df_recent)) * 100)
df_recent.shape

df_recent

"""# Régression linéaire simple"""

import statsmodels.api as sm

X = sm.add_constant(df_recent["OilVol_OVX"])
y = df_recent["MktVol_VIX"]

ols = sm.OLS(y, X).fit()

print(ols.summary())

"""Sans parler, d'effet causal, nous observons une très forte corrélation entre les deux variables, ce qui est un bon point de départ car sans corrélation, pas de causalité.

# Régression avec toutes les variables de contrôle
"""

cols = [
    "OilVol_OVX",
    "Stress_STLFSI",
    "Spread_TED",
    "PCE_Price_Index",
    "Unemployment_Rate",
    "Industrial_Production",
    "Recession_Prob_Smoothed",
    "Dollar_Broad_Index",
    "Uncertainty_EPU_US",
    "CPI_AllItems",
    "Spread_US_Corp_OAS",
    "FX_USD_EUR"]

X = sm.add_constant(df_recent[cols])
y = df_recent["MktVol_VIX"]

ols = sm.OLS(y, X).fit()
print(ols.summary())

"""Nos variables de contrôle permettent d'augmenter la significativité de notre modèle en captant une partie des erreurs auparavant comprises dans les résidus et probablement corrélées avec notre variable explicative principale (car la valeur t baisse beaucoup). Le R-carré est incr."""

import matplotlib.pyplot as plt

residuals = ols.resid
x_main = df_recent["OilVol_OVX"]

plt.figure(figsize=(8,5))
plt.scatter(x_main, residuals, alpha=0.6, edgecolors="k")
plt.axhline(y=0, color='red', linestyle='--', linewidth=1)
plt.xlabel("Oil volatility (OilVol_OVX)")
plt.ylabel("Model residuals")
plt.title("Residuals vs oil volatility")
plt.grid(True, linestyle=':', alpha=0.6)

# Sauvegarde de l'image
plt.savefig("residuals_vs_oilvol.png", dpi=300, bbox_inches="tight")

plt.show()

"""On déduit du graphique « Test visuel d’homoscedasticité : résidus vs valeurs prédites », que nous avons de l’heteroscedasticité dans nos données étant donné que la variance n’est pas constante en fonction du prix du pétrole. Ainsi l’estimations classique de la variance de nos coefficient sera biaisé. Il faudra donc estimer cette meme variance sous sa forme robuste. Nous ferons de même par précaution pour toutes les prochaines spécifications de notre modèle étant donné que la variance robuste est aussi valable dans le cas d’homoscedasticité.

De plus, une autocorrélation des résidus est fortemment probable (voir confirmée par le test Durbin-Watson). Nous allons donc utiliser les erreurs HAC.

# Régression avec toutes les variables de contrôle avec contrôle pour HAC.
"""

cols = [
    "OilVol_OVX",
    "Stress_STLFSI",
    "Spread_TED",
    "PCE_Price_Index",
    "Unemployment_Rate",
    "Industrial_Production",
    "Recession_Prob_Smoothed",
    "Dollar_Broad_Index",
    "Uncertainty_EPU_US",
    "CPI_AllItems",
    "Spread_US_Corp_OAS",
    "FX_USD_EUR"
]

X = sm.add_constant(df_recent[cols])
y = df_recent["MktVol_VIX"]

ols = sm.OLS(y, X).fit()

ols_hac = ols.get_robustcov_results(cov_type='HAC', maxlags=5)

print(ols_hac.summary())

"""Puisque nous avons des données journalières, nous considérons qu'il faut contrôler l'autocorrélation sur plusieurs périodes (jours). Nous avons arbitrairement choisi de prendre le nombre de jour ou l'autocorrélation était possible à 5, ce qui équivaut à une semaine d'ouverture des marchés.

Nous voyons que pour l'instant le coefficient n'est pas significatif à 5% -> on continue l'analyse.

# Matrice de correlation entre prix du petrole et les differentes variables explicative
"""

import seaborn as sns

df_recent.head(1)
correlation_with_oilvol = df_recent.corr()['OilVol_OVX']

#matrice de corr
control_var = ["MktVol_VIX","OilVol_OVX","Spread_US_Corp_OAS","Stress_STLFSI","Spread_TED","CPI_AllItems","PCE_Price_Index","Unemployment_Rate","Industrial_Production","Recession_Prob_Smoothed","FX_USD_EUR","Dollar_Broad_Index","Uncertainty_EPU_US"]

df_control = df_recent[control_var]
cov_matrix = df_control.corr()


# heatmap
plt.figure(figsize=(8,6))
sns.heatmap(cov_matrix, annot=True, cmap='coolwarm', fmt=".2f")
plt.title("Covariance Matrix of Control Variables")
plt.show()

"""Explication de pourquoi on enlève certaines variables de contrôle dans la prochaine régression : On voit sur la heat map que CPI_ALLTERM et PCE_Price_Index sont fortement corrélé / sont identique ( meme choses ) donc on enlève un des deux ( n’importe lequel ) ici on a enlever CPI allterm.

Ensuite on voit que la corrélation entre STRESS_STLFSI et spread us corp sont tres corréler on enlève donc un des deux.

ON decide d’enlever les variables de controles peu corrélées avec notre variable dépendante pour ne pas perdre trop de degrés de liberté. Ce qui serait le cas si nous avions énormément de variables explicatives sans vraiment bcp de pertinence.

On enlève donc le taux de change FX_USD_EUR qui est tres faiblement corrélée avec la volatilité.

# Deuxième régression en enlevant certaines variables de contrôle pour éviter perte de degrés de liberté grâce à la matrice de correlation.
"""

cols = [
    "OilVol_OVX",
    "Stress_STLFSI",
    "PCE_Price_Index",
    "Spread_TED",
    "Recession_Prob_Smoothed",
    "Uncertainty_EPU_US",
    "Unemployment_Rate",
    "Dollar_Broad_Index",
    "Industrial_Production"]

X = sm.add_constant(df_recent[cols])
y = df_recent["MktVol_VIX"]

ols = sm.OLS(y, X).fit()

ols_hac = ols.get_robustcov_results(cov_type='HAC', maxlags=5)

print(ols_hac.summary())

"""Le coefficient devient plus significatif (à 5% il l'est) grâce au changement de variables de contrôle.

Malgré le fait d'avoir enlevé les variables de contrôle trop fortemment corrélées entre elles, nous voyons grace aux condition number que la multicolinearite entre nos variables explicatives est forte. Dans la suit de notre étude nous serons conscient du fait que la variance de nos coéfficients sera probablement surestimée a cause de cette multicolinéarité. Cela représenterait un problème dans le cas ou nous ne rejetons pas l’hypothèse nulle de non significativité du coefficient, et qu’ainsi si nous rejetons malgré tout l’hypothèse nulle sur un certain coefficient, ce résultat pourrait être interpreter comme non, biaisé par la multicolinearité.

# Regression avec effets d'interaction
"""

df_recent["OilVol_OVX_x_Stress_STLFSI"] = df_recent["OilVol_OVX"] * df_recent["Stress_STLFSI"]
df_recent["OilVol_OVX_x_Spread_TED"] = df_recent["OilVol_OVX"] * df_recent["Spread_TED"]
df_recent["OilVol_OVX_x_Dollar_Broad_Index"] = df_recent["OilVol_OVX"] * df_recent["Dollar_Broad_Index"]
df_recent["OilVol_OVX_x_Yield_US3M"] = df_recent["OilVol_OVX"] * df_recent["Yield_US3M"]
df_recent["OilVol_OVX_x_Uncertainty_EPU_US"] = df_recent["OilVol_OVX"] * df_recent["Uncertainty_EPU_US"]


cols_with_interaction = [
    "OilVol_OVX",
    "Stress_STLFSI",
    "Spread_TED",
    "PCE_Price_Index",
    "Unemployment_Rate",
    "Industrial_Production",
    "Recession_Prob_Smoothed",
    "Dollar_Broad_Index",
    "Uncertainty_EPU_US",
    "OilVol_OVX_x_Stress_STLFSI",
    "OilVol_OVX_x_Dollar_Broad_Index",
    "OilVol_OVX_x_Yield_US3M",
    "OilVol_OVX_x_Uncertainty_EPU_US"
]
X = sm.add_constant(df_recent[cols_with_interaction])
y = df_recent["MktVol_VIX"]

ols_two = sm.OLS(y, X).fit()

ols_two_hac = ols_two.get_robustcov_results(cov_type='HAC', maxlags =5)

print(ols_two_hac.summary())

"""Ici on a essayer de regresser les variables d'interaction dans notre modele. Intuitivement on a selectionné les variables d'interactions ci jointe au sein du vecteur cols_with_interaction.

Intuitivement, on a pris ces effets d'interraction par notre connaissance du domaine.

On voit que les effets d'interraction changent énormément la significativité du coefficient (interpréter cela avec les effets d'interraction).

- OilVol_OVX_x_Stress_STLFSI : Nous partons donc du principe que lorsque le stress sur les marchés est élevé cela a un impact sur l’effet de la volatilité du marché du pétrole sur la volatilité globale du marché ( nous nous attendons a un effet positif ). On voit cependant que cet effet d’interaction est negatif dans les données.
- OilVol_OVX_x_Dollar_Broad_Index : Quand le dollar americain est élevé les matières premiere libelles en USD dfeviennent plus cheres pour les autres pays, la demande de petrole tend donc a baisser ce qui est percu comme un signal de resserrement, l’effet de la volatilité du petrole sur la volatilité du marché augmente. Ce qui est le cas empiriquement.
- OilVol_OVX_x_Yield_US3M : Le petrole explique moins la volatilité du marché quand le taux sans risque est haut car le marché est déja nerveux à cause des taux et donc la volatilité sur le marché est plus élevé. A l’inverse lorsque les taux sont faible le marché est serein, donc une volatilité plus élevée du petrole aura un impact plus élevé
- OilVol_OVX_x_Uncertainty_EPU_US : Lorsque l’incertitude est élevé, le marché est deja nerveux, ainsi une augmentation de la volatilité du marché du pétrole a moins d’effet sur la volatilité du marché.

# Troisième régression avec effet quadratique (quand la volalitilité du pétrole est déjà élevée, un effet marginal a plus d'impact sur la volatilité du marché)
"""

df_recent["OilVol_OVX_sq"] = df_recent["OilVol_OVX"] ** 2

cols_quad = [
    "OilVol_OVX",
    "OilVol_OVX_sq",
    "Stress_STLFSI",
    "Spread_TED",
    "PCE_Price_Index",
    "Unemployment_Rate",
    "Industrial_Production",
    "Recession_Prob_Smoothed",
    "Dollar_Broad_Index",
    "Uncertainty_EPU_US",
    "OilVol_OVX_x_Stress_STLFSI",
    "OilVol_OVX_x_Dollar_Broad_Index",
    "OilVol_OVX_x_Yield_US3M",
    "OilVol_OVX_x_Uncertainty_EPU_US",

]

X = sm.add_constant(df_recent[cols_quad].dropna())
y = df_recent.loc[X.index, "MktVol_VIX"]

ols_quad = sm.OLS(y, X).fit()
ols_quad_hac = ols_quad.get_robustcov_results(cov_type='HAC', maxlags=5)

print(ols_quad_hac.summary())

"""Nous pouvions penser qu'un effet quadratique serait significatif car nous pension à une non-linéarité de l'effet de la volatilité du prix du pétrole mais ce n'est pas le cas (broder les frérots). Nous décidons donc de ne pas inclure d'effet quadratique afin de ne pas perdre de DDL inutiles."""

import statsmodels.formula.api as smf
import numpy as np

Xvars = [
    "OilVol_OVX",
    "Stress_STLFSI",
    "Spread_TED",
    "PCE_Price_Index",
    "Unemployment_Rate",
    "Industrial_Production",
    "Recession_Prob_Smoothed",
    "Dollar_Broad_Index",
    "Uncertainty_EPU_US"
]

d = df_recent.dropna(subset=["MktVol_VIX"] + Xvars).copy()

f_lin = "MktVol_VIX ~ " + " + ".join(Xvars)
m_lin = smf.ols(f_lin, data=d).fit()
d["_yhat2"] = m_lin.fittedvalues**2
m_aux_lin = smf.ols(f_lin + " + _yhat2", data=d).fit()

pos = (d[["MktVol_VIX"] + Xvars] > 0).all(axis=1)
dl = d.loc[pos].copy()
for v in ["MktVol_VIX"] + Xvars:
    dl["ln" + v] = np.log(dl[v])

f_log = "lnMktVol_VIX ~ " + " + ".join("ln" + v for v in Xvars)
m_log = smf.ols(f_log, data=dl).fit()
dl["_yhat2"] = m_log.fittedvalues**2
m_aux_log = smf.ols(f_log + " + _yhat2", data=dl).fit()

print("PE Linear:   t(_yhat2) =", round(m_aux_lin.tvalues["_yhat2"], 3),
      " p =", round(m_aux_lin.pvalues["_yhat2"], 4))
print("PE Log-lin:  t(_yhat2) =", round(m_aux_log.tvalues["_yhat2"], 3),
      " p =", round(m_aux_log.pvalues["_yhat2"], 4))

print("\nAdj.R² Linear:", round(m_lin.rsquared_adj, 4),
      " | Adj.R² Log-lin:", round(m_log.rsquared_adj, 4))

"""Comme nous pouvons le voir en effectuant le PE test, un modèle log-linéaire est plus judicieux, le R_carré ajusté étant plus grand et les tests rejettant à chaque fois l'hypothèse de linéarité. Pour le premier test, H0 = modèle linéaire et H1 = modèle non linéaire et pour le deuxième test : H0 = modèle non linéaire H1 = modèle linéaire."""

Xvars = [
    "OilVol_OVX",
    "Stress_STLFSI",
    "Spread_TED",
    "PCE_Price_Index",
    "Unemployment_Rate",
    "Industrial_Production",
    "Recession_Prob_Smoothed",
    "Dollar_Broad_Index",
    "Uncertainty_EPU_US"
]

df_log = df_recent.dropna(subset=["MktVol_VIX"] + Xvars).copy()
df_log = df_log[(df_log[["MktVol_VIX"] + Xvars] > 0).all(axis=1)].copy()

for v in ["MktVol_VIX"] + Xvars:
    df_log["ln" + v] = np.log(df_log[v])

formula = "lnMktVol_VIX ~ " + " + ".join("ln" + v for v in Xvars)

m_log = smf.ols(formula, data=df_log).fit()
m_log_hac = m_log.get_robustcov_results(cov_type="HAC", maxlags =5)

print(m_log_hac.summary())

"""Voici la régression log-linéaire que l'on a mise en place grâce au prédécent PE-test.

- quand la vol du prix du pétrole augmente de 1% la volatilité du marché augmente de 0,6944%
- l’erreur standarrd robuste represente 14,68% de notre coefficient ce qui est correct.

Il faut interpréter les coefficients, les intervalles de confiance etc etc.

Etant donné la structure de nos données nous nous sommes poser la question de la possibilité de controler pour des effets fixes temporels. Ces effets fixes permettrait pour chaque période d’indiquer l’effet propre de la période sur la volatilité du marché. Ceci nous permettrait donc de gagner en accuracy. Or, cette modélisation nous ferait perdre des degrés de libertés, ce cout serait moindre mais reel tout de meme. Cependant nous avons au sein de notre modele la variable « recession_Prob_Smoothed » qui mesure la probabilité sous forme de ratio d’une recession a un temps donné t. Cette variable nous donne ainsi une forte indication de l’effet fixe du contexte de la période sur la volatilité du marché, ainsi nous ne prenons pas le risque d’avoir un cout en terme de degré de liberté en implémentant des effets fixes temporelles propre a chacun des 10 années de nos données.

Nous pouvons également souligné le fait que la spécification log-log est cohérente avec la littérature ainsi que notre interprétation de l'effet de la volatilité du pétrole sur la volatilité du marché -> en effet,

Inférence causale : Il faut mentionner que le modèle pourrait soufrir d'un biais de simultanéité car la volatilité du marché peut influencer la volatilité du pétrole. Il faudrait alors utiliser des variables instrumentales pour contrôler cela. **Idées de variables instrumentales : volatilité du Brent (car moins affectée par le marché US mais corrélée avec oil_OVX aus us), volatilité géopolitique des pays producteurs, chocs d'offres physiques (affecte le pétrole mais n'est pas affecté par le marché)

Prédiction : même dans un cas de prédiction, le modèle est imparfait car il faudrait ajouter une composante dynamique (dans le sens ou peut-être que c'est la volatilité j-1 ou j-2 du pétrole qui explique mieux la volatilité j du marché.
"""

