"""Patch _head.html: insert client-side i18n system before </head>."""
import pathlib, sys

p = pathlib.Path(r"C:\Users\hugo1\Desktop\SAINHE\repo\templates\partials\_head.html")
raw = p.read_bytes()

INSERT = """
  <!-- i18n CLIENT-SIDE SYSTEM -->
  <script>
  /* == 1. Synchronous init == */
  (function(){
    var LOCALES={en:'en-US',fr:'fr-FR',de:'de-DE',es:'es-ES',zh:'zh-CN',ru:'ru-RU',ja:'ja-JP'};
    var lang='en';
    try{var s=localStorage.getItem('sainhe_lang');if(s&&LOCALES[s])lang=s;}catch(e){}
    window.SAINHE_LANG  =lang;
    window.SAINHE_LOCALE=LOCALES[lang]||'en-US';
    window.SAINHE_I18N  ={};
    if(lang!=='en'){
      try{var raw=localStorage.getItem('sainhe_i18n_'+lang);if(raw)window.SAINHE_I18N=JSON.parse(raw);}catch(e){}
    }
    document.documentElement.lang=lang;
  })();

  /* == 2. translatePage == */
  function translatePage(){
    var I18N=window.SAINHE_I18N||{};
    if(!Object.keys(I18N).length)return;
    document.querySelectorAll('[data-i18n]').forEach(function(el){
      var k=el.getAttribute('data-i18n');if(I18N[k])el.textContent=I18N[k];
    });
    document.querySelectorAll('[data-i18n-title]').forEach(function(el){
      var k=el.getAttribute('data-i18n-title');if(I18N[k])el.title=I18N[k];
    });
    document.querySelectorAll('[data-i18n-aria]').forEach(function(el){
      var k=el.getAttribute('data-i18n-aria');if(I18N[k])el.setAttribute('aria-label',I18N[k]);
    });
    /* update lang button + active marker */
    var btn=document.getElementById('dd-lang-btn');
    if(btn){var t=btn.childNodes[0];if(t&&t.nodeType===3)t.nodeValue=window.SAINHE_LANG.toUpperCase();}
    document.querySelectorAll('#dd-lang .hdr-dd-item').forEach(function(el){
      el.classList.toggle('active',el.dataset.lang===window.SAINHE_LANG);
    });
  }

  /* == 3. setLang == */
  function setLang(code){
    var LOCALES={en:'en-US',fr:'fr-FR',de:'de-DE',es:'es-ES',zh:'zh-CN',ru:'ru-RU',ja:'ja-JP'};
    if(!LOCALES[code])return;
    try{localStorage.setItem('sainhe_lang',code);}catch(e){}
    if(code==='en'){location.reload();return;}
    var cached=null;
    try{cached=localStorage.getItem('sainhe_i18n_'+code);}catch(e){}
    if(cached){location.reload();}
    else{
      fetch('/locales/'+code+'.json')
        .then(function(r){return r.json();})
        .then(function(data){
          try{localStorage.setItem('sainhe_i18n_'+code,JSON.stringify(data));}catch(e){}
          location.reload();
        })
        .catch(function(){location.reload();});
    }
  }

  /* == 4. DOMContentLoaded == */
  document.addEventListener('DOMContentLoaded',function(){
    translatePage();
    /* cache-miss: non-EN but no cached translations yet */
    if(window.SAINHE_LANG!=='en'&&!Object.keys(window.SAINHE_I18N).length){
      fetch('/locales/'+window.SAINHE_LANG+'.json')
        .then(function(r){return r.json();})
        .then(function(data){
          window.SAINHE_I18N=data;
          try{localStorage.setItem('sainhe_i18n_'+window.SAINHE_LANG,JSON.stringify(data));}catch(e){}
          translatePage();
          ['_sainheRenderMacro','_sainheRenderIndices','_sainheRenderPortfolio',
           '_sainheRenderSentiment','_sainheRenderSectors','_sainheRenderNews']
            .forEach(function(fn){window[fn]&&window[fn]();});
        });
    }
  });
  </script>
</head>"""

target = b'</head>'
if target not in raw:
    print("ERROR: </head> not found", file=sys.stderr)
    sys.exit(1)

idx = raw.rfind(target)
new_raw = raw[:idx] + INSERT.encode('utf-8')
p.write_bytes(new_raw)
print(f"OK: _head.html patched ({len(new_raw)} bytes, was {len(raw)})")
