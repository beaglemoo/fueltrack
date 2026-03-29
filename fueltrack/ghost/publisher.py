"""Ghost page publisher - updates fuel prices page on sillymoo.dev."""

import html
import json
import logging
import time
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from ..api.models import Station
from ..collectors.prices import classify_station, extract_brand, extract_location
from ..config import RegionConfig

logger = logging.getLogger(__name__)


def _build_token(api_key: str) -> str:
    """Build a Ghost Admin API JWT token."""
    import jwt

    key_id, secret = api_key.split(":")
    iat = int(time.time())
    header = {"alg": "HS256", "typ": "JWT", "kid": key_id}
    payload = {"iat": iat, "exp": iat + 300, "aud": "/admin/"}
    return jwt.encode(payload, bytes.fromhex(secret), algorithm="HS256", headers=header)


def _format_price(price: float | None) -> str:
    """Format price for display."""
    if price is None:
        return "-"
    if price < 10:
        return f"{price}p"
    return f"{price:.1f}p"


def _esc(text: str) -> str:
    """HTML-escape a string."""
    return html.escape(text, quote=True)


_PAGE_CSS = """<style>
.ft-search-wrap{margin:0 0 1.5em;position:sticky;top:0;z-index:10;background:#1a1a2e;padding:1em;border-radius:8px}
.ft-search{width:100%;padding:12px 16px;font-size:1.1em;border:2px solid rgba(255,255,255,0.2);border-radius:6px;background:rgba(255,255,255,0.1);color:#fff;outline:none;box-sizing:border-box}
.ft-search::placeholder{color:rgba(255,255,255,0.5)}
.ft-search:focus{border-color:rgba(255,255,255,0.5)}
.ft-meta{display:flex;justify-content:space-between;align-items:center;margin-top:8px;font-size:0.85em;color:rgba(255,255,255,0.7);flex-wrap:wrap;gap:8px}
.ft-sort{display:flex;gap:4px;flex-wrap:wrap}
.ft-sort button{background:rgba(255,255,255,0.15);border:none;color:#fff;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:0.85em}
.ft-sort button.active{background:rgba(255,255,255,0.35)}
.ft-results table{width:100%;border-collapse:collapse;font-size:0.9em}
.ft-results th{text-align:left;padding:8px 6px;border-bottom:2px solid rgba(255,255,255,0.2);font-size:0.8em;text-transform:uppercase;letter-spacing:0.05em}
.ft-results td{padding:6px;border-bottom:1px solid rgba(255,255,255,0.07)}
.ft-results tr:nth-child(even){background:rgba(255,255,255,0.03)}
.ft-results .price{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.ft-results .cheap{color:#4caf50;font-weight:bold}
.ft-more{display:block;width:100%;padding:10px;margin:1em 0;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);color:#fff;border-radius:6px;cursor:pointer;font-size:0.95em;text-align:center}
.ft-more:hover{background:rgba(255,255,255,0.2)}
.ft-prompt{text-align:center;padding:2em 1em;color:rgba(255,255,255,0.5);font-size:1.1em}
.ft-loc{font-size:0.8em;color:rgba(255,255,255,0.5);display:block}
.ft-brands{display:flex;gap:4px;flex-wrap:wrap;margin-top:8px}
.ft-brands button{background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.15);color:rgba(255,255,255,0.7);padding:4px 10px;border-radius:4px;cursor:pointer;font-size:0.8em;white-space:nowrap}
.ft-brands button.active{background:rgba(255,255,255,0.3);color:#fff;border-color:rgba(255,255,255,0.3)}
.ft-stats{font-size:0.8em;color:rgba(255,255,255,0.5);margin-top:6px}
.ft-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px;vertical-align:middle}
.ft-dot-fresh{background:#4caf50}
.ft-dot-mid{background:#ff9800}
.ft-dot-stale{background:#666}
.ft-age{font-size:0.75em;color:rgba(255,255,255,0.4);margin-left:4px}
.ft-map{color:inherit;text-decoration:none;border-bottom:1px dotted rgba(255,255,255,0.3)}
.ft-map:hover{border-bottom-color:rgba(255,255,255,0.6)}
@media(max-width:600px){
.ft-results .hide-mobile{display:none}
.ft-results td,.ft-results th{padding:4px 3px;font-size:0.8em}
.ft-search{font-size:16px}
.ft-sort button,.ft-brands button{min-height:44px;padding:8px 12px}
.ft-brands{overflow-x:auto;-webkit-overflow-scrolling:touch;flex-wrap:nowrap}
}
</style>"""

_PAGE_JS = """<script>
(function(){
var hook=document.getElementById('search-all-stations');
if(!hook)return;

var app=document.createElement('div');
app.id='ft-app';
hook.parentNode.insertBefore(app,hook.nextSibling);

app.innerHTML='<div class="ft-prompt">Loading station data...</div>';
fetch('/content/files/stations.json')
.then(function(r){if(!r.ok)throw new Error(r.status);return r.json();})
.then(function(S){initApp(S);})
.catch(function(e){app.innerHTML='<div class="ft-prompt">Failed to load station data. Please try refreshing.</div>';});

function initApp(S){
if(!S.length)return;
hook=app;

hook.innerHTML='<div class="ft-search-wrap">'
+'<input type="text" id="ft-search" class="ft-search" placeholder="Search by station name, brand, or location..." autocomplete="off">'
+'<div class="ft-meta"><span id="ft-count"></span>'
+'<div class="ft-sort">Sort: '
+'<button data-col="e" class="active">Unleaded</button>'
+'<button data-col="d">Diesel</button>'
+'<button data-col="s">Super</button>'
+'<button data-col="n">Name</button>'
+'</div></div>'
+'<div class="ft-brands" id="ft-brands"></div>'
+'<div class="ft-stats" id="ft-stats"></div>'
+'</div>'
+'<div class="ft-results">'
+'<div id="ft-prompt" class="ft-prompt">Type a location, station name, or brand to search all UK fuel prices</div>'
+'<table><thead><tr>'
+'<th>Station</th><th>Brand</th>'
+'<th>Unleaded</th><th class="hide-mobile">Super</th>'
+'<th>Diesel</th><th class="hide-mobile">Premium</th>'
+'</tr></thead><tbody id="ft-body"></tbody></table>'
+'<button id="ft-more" class="ft-more" style="display:none">Show more</button>'
+'</div>';

var input=document.getElementById('ft-search');
var tbody=document.getElementById('ft-body');
var countEl=document.getElementById('ft-count');
var moreBtn=document.getElementById('ft-more');
var promptEl=document.getElementById('ft-prompt');
var statsEl=document.getElementById('ft-stats');
var sortBtns=hook.querySelectorAll('.ft-sort button');
var filtered=[];
var limit=100;
var sortCol='e';
var sortAsc=true;
var brandFilter='';
var timer=null;

// Build brand filter buttons
var brands=['Shell','BP','Esso','Tesco','Sainsburys','ASDA','Morrisons','Costco','Jet','MFG'];
var brandsEl=document.getElementById('ft-brands');
var allBtn=document.createElement('button');
allBtn.textContent='All';allBtn.className='active';allBtn.setAttribute('data-brand','');
brandsEl.appendChild(allBtn);
brands.forEach(function(b){
  var btn=document.createElement('button');btn.textContent=b;btn.setAttribute('data-brand',b);
  brandsEl.appendChild(btn);
});
brandsEl.addEventListener('click',function(ev){
  if(ev.target.tagName!=='BUTTON')return;
  brandFilter=ev.target.getAttribute('data-brand');
  brandsEl.querySelectorAll('button').forEach(function(b){b.classList.remove('active');});
  ev.target.classList.add('active');
  filter();
});

function fmt(v){if(v==null)return'-';return v<10?v+'p':v.toFixed(1)+'p';}

function age(epoch){
  if(!epoch)return'';
  var s=Math.floor(Date.now()/1000-epoch);
  if(s<3600)return Math.floor(s/60)+'m ago';
  if(s<86400)return Math.floor(s/3600)+'h ago';
  return Math.floor(s/86400)+'d ago';
}

function dotClass(epoch){
  if(!epoch)return'ft-dot ft-dot-stale';
  var h=(Date.now()/1000-epoch)/3600;
  if(h<24)return'ft-dot ft-dot-fresh';
  if(h<72)return'ft-dot ft-dot-mid';
  return'ft-dot ft-dot-stale';
}

function updateStats(){
  if(!filtered.length){statsEl.textContent='';return;}
  var key=sortCol==='n'?'e':sortCol;
  var vals=filtered.map(function(s){return s[key];}).filter(function(v){return v!=null;});
  if(!vals.length){statsEl.textContent='';return;}
  var mn=Math.min.apply(null,vals),mx=Math.max.apply(null,vals);
  var avg=vals.reduce(function(a,b){return a+b;},0)/vals.length;
  var label={e:'Unleaded',d:'Diesel',s:'Super',p:'Premium'}[key]||'Price';
  statsEl.textContent=label+': Avg '+avg.toFixed(1)+'p | Cheapest '+mn.toFixed(1)+'p | Range '+mn.toFixed(1)+'p - '+mx.toFixed(1)+'p';
}

function render(){
  var frag=document.createDocumentFragment();
  var show=filtered.slice(0,limit);
  tbody.textContent='';
  for(var i=0;i<show.length;i++){
    var s=show[i];
    var tr=document.createElement('tr');
    var c=function(t,cls){var td=document.createElement('td');td.textContent=t;if(cls)td.className=cls;return td;};
    var nameCell=document.createElement('td');
    var a=document.createElement('a');
    a.href='https://www.google.com/maps/search/'+encodeURIComponent(s.n);
    a.target='_blank';a.rel='noopener';a.className='ft-map';a.textContent=s.n;
    nameCell.appendChild(a);
    if(s.l&&s.l!==s.n){var loc=document.createElement('span');loc.className='ft-loc';loc.textContent=s.l;nameCell.appendChild(loc);}
    if(s.u){var dot=document.createElement('span');dot.className=dotClass(s.u);dot.title='Updated '+age(s.u);nameCell.appendChild(dot);
    var ageSpan=document.createElement('span');ageSpan.className='ft-age';ageSpan.textContent=age(s.u);nameCell.appendChild(ageSpan);}
    tr.appendChild(nameCell);
    tr.appendChild(c(s.b,''));
    tr.appendChild(c(fmt(s.e),'price'+(s._ce?' cheap':'')));
    var superCell=c(fmt(s.s),'price hide-mobile');tr.appendChild(superCell);
    tr.appendChild(c(fmt(s.d),'price'+(s._cd?' cheap':'')));
    var premCell=c(fmt(s.p),'price hide-mobile');tr.appendChild(premCell);
    frag.appendChild(tr);
  }
  tbody.appendChild(frag);
  countEl.textContent=filtered.length===S.length?filtered.length.toLocaleString()+' stations':filtered.length.toLocaleString()+' matches';
  moreBtn.style.display=filtered.length>limit?'block':'none';
  if(filtered.length>limit)moreBtn.textContent='Show more ('+Math.min(100,filtered.length-limit)+' of '+(filtered.length-limit)+' remaining)';
  promptEl.style.display=(filtered.length===0&&input.value.length===0)?'block':'none';
  updateStats();
}

function doSort(){
  filtered.sort(function(a,b){
    var va=a[sortCol],vb=b[sortCol];
    if(va==null&&vb==null)return 0;
    if(va==null)return 1;
    if(vb==null)return-1;
    if(typeof va==='string')return sortAsc?va.localeCompare(vb):vb.localeCompare(va);
    return sortAsc?va-vb:vb-va;
  });
}

function markCheapest(){
  var minE=Infinity,minD=Infinity;
  for(var i=0;i<filtered.length;i++){
    if(filtered[i].e!=null&&filtered[i].e<minE)minE=filtered[i].e;
    if(filtered[i].d!=null&&filtered[i].d<minD)minD=filtered[i].d;
    filtered[i]._ce=false;filtered[i]._cd=false;
  }
  for(var i=0;i<filtered.length;i++){
    if(filtered[i].e===minE)filtered[i]._ce=true;
    if(filtered[i].d===minD)filtered[i]._cd=true;
  }
}

function filter(){
  var q=input.value.toLowerCase().trim();
  limit=100;
  var base=brandFilter?S.filter(function(s){return s.b===brandFilter;}):S;
  if(q===''){filtered=base.slice();}
  else{
    var terms=q.split(/\\s+/);
    filtered=base.filter(function(s){
      var hay=(s.n+'|'+s.b+'|'+(s.l||'')).toLowerCase();
      return terms.every(function(t){return hay.indexOf(t)>=0;});
    });
  }
  doSort();markCheapest();render();
}

input.addEventListener('input',function(){clearTimeout(timer);timer=setTimeout(filter,200);});
moreBtn.addEventListener('click',function(){limit+=100;render();});
sortBtns.forEach(function(btn){
  btn.addEventListener('click',function(){
    var col=this.getAttribute('data-col');
    if(sortCol===col){sortAsc=!sortAsc;}else{sortCol=col;sortAsc=col==='n'||col==='b';}
    sortBtns.forEach(function(b){b.classList.remove('active');});
    this.classList.add('active');
    doSort();render();
  });
});

promptEl.style.display='block';
countEl.textContent=S.length.toLocaleString()+' stations';
}
})();
</script>"""


def generate_page_data(
    stations: list[Station],
    regions: list[RegionConfig],
    fuel_types: list[str],
) -> dict:
    """Generate HTML content, CSS, and JS for the Ghost fuel prices page.

    Returns dict with keys: html, codeinjection_head, codeinjection_foot
    """
    now = datetime.now(timezone.utc).strftime("%d %B %Y at %H:%M UTC")

    # Build station data with classification
    station_rows = []
    for s in stations:
        if not s.fuel_prices:
            continue
        region = classify_station(s, regions)
        brand = extract_brand(s.trading_name)
        location = extract_location(s.trading_name)
        prices = {fp.fuel_type: fp.price for fp in s.fuel_prices}

        # Skip stations with obviously wrong prices (< 50p or > 300p)
        valid_prices = {k: v for k, v in prices.items() if 50 < v < 300}
        if not valid_prices:
            continue

        # Get most recent price update timestamp
        max_updated = max(
            (fp.price_last_updated for fp in s.fuel_prices if fp.price),
            default=None,
        )

        station_rows.append({
            "name": s.trading_name,
            "brand": brand,
            "location": location,
            "region": region,
            "prices": valid_prices,
            "updated": max_updated,
        })

    # Sort by cheapest E10, then B7_STANDARD
    def sort_key(s):
        return s["prices"].get("E10", s["prices"].get("B7_STANDARD", 999))

    station_rows.sort(key=sort_key)

    # Build compact JSON data for client-side search
    json_data = []
    for row in station_rows:
        entry = {
            "n": row["name"],
            "b": row["brand"],
            "l": row["location"],
            "e": row["prices"].get("E10"),
            "s": row["prices"].get("E5"),
            "d": row["prices"].get("B7_STANDARD"),
            "p": row["prices"].get("B7_PREMIUM"),
        }
        if row["updated"]:
            entry["u"] = int(row["updated"].timestamp())
        json_data.append(entry)

    # Build HTML (only Ghost-safe elements - no script/style/input/button)
    parts = []

    # Header
    parts.append(f'<p><strong>Last updated:</strong> {now}</p>')
    parts.append(f'<p><strong>{len(station_rows):,} stations</strong> reporting prices across the UK. '
                 'Data from the <a href="https://www.fuel-finder.service.gov.uk/">GOV.UK Fuel Finder</a>. '
                 'Prices update within 30 minutes of changes at the pump. '
                 'This page refreshes every 4 hours.</p>')

    # Use a heading as anchor - Ghost preserves h2 with auto-generated IDs
    parts.append('<h2>Search All Stations</h2>')
    parts.append(f'<p>Search and compare current fuel prices across {len(station_rows):,} '
                 'UK petrol stations. Filter by brand, sort by price, and find the '
                 'cheapest fuel near you.</p>')

    # National top 10 cheapest per fuel type
    top_n = 10
    fuel_type_labels = [
        ("E10", "Unleaded (E10)"),
        ("B7_STANDARD", "Diesel"),
        ("E5", "Super Unleaded (E5)"),
        ("B7_PREMIUM", "Premium Diesel"),
    ]
    for ft_code, ft_label in fuel_type_labels:
        ft_sorted = [(s, s["prices"][ft_code]) for s in station_rows if ft_code in s["prices"]]
        if not ft_sorted:
            continue
        ft_sorted.sort(key=lambda x: x[1])
        parts.append('<hr>')
        parts.append(f'<h2>UK Top {top_n} Cheapest - {ft_label}</h2>')
        parts.append('<table>')
        parts.append('<thead><tr><th>#</th><th>Station</th><th>Brand</th><th>Price</th></tr></thead>')
        parts.append('<tbody>')
        for i, (s, price) in enumerate(ft_sorted[:top_n], 1):
            maps_url = f'https://www.google.com/maps/search/{quote(s["name"])}'
            name_link = f'<a href="{maps_url}" target="_blank" rel="noopener">{_esc(s["name"])}</a>'
            parts.append(f'<tr><td>{i}</td><td>{name_link}</td><td>{_esc(s["brand"])}</td><td>{price:.1f}p</td></tr>')
        parts.append('</tbody></table>')

    # Footer
    parts.append('<hr>')
    parts.append('<p><small>Powered by <a href="https://github.com/beaglemoo/fueltrack">FuelTrack</a> '
                 '| Data: GOV.UK Fuel Finder (Open Government Licence v3.0) '
                 '| Updates every 4 hours</small></p>')

    # Build dynamic structured data for SEO
    now_iso = datetime.now(timezone.utc).isoformat()

    dataset_schema = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "UK Fuel Prices",
        "description": f"Current fuel prices at over {len(station_rows):,} UK petrol stations, updated every 4 hours",
        "url": "https://sillymoo.dev/uk-fuel-prices/",
        "license": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        "creator": {"@type": "Person", "name": "James"},
        "dateModified": now_iso,
        "temporalCoverage": "..",
        "keywords": ["UK fuel prices", "petrol prices", "diesel prices", "cheapest petrol", "fuel price comparison"],
        "spatialCoverage": {
            "@type": "Place",
            "name": "United Kingdom",
            "geo": {"@type": "GeoShape", "box": "49.9 -8.6 60.9 1.8"},
        },
        "distribution": {
            "@type": "DataDownload",
            "encodingFormat": "application/json",
            "contentUrl": "https://sillymoo.dev/content/files/stations.json",
        },
        "variableMeasured": [
            {"@type": "PropertyValue", "name": "Unleaded (E10)", "unitText": "pence per litre"},
            {"@type": "PropertyValue", "name": "Diesel (B7)", "unitText": "pence per litre"},
            {"@type": "PropertyValue", "name": "Super Unleaded (E5)", "unitText": "pence per litre"},
            {"@type": "PropertyValue", "name": "Premium Diesel (B7 Premium)", "unitText": "pence per litre"},
        ],
        "isBasedOn": {
            "@type": "GovernmentService",
            "name": "GOV.UK Fuel Finder",
            "url": "https://www.fuel-finder.service.gov.uk/",
        },
    }

    # Dynamic FAQ answers
    cheapest_e10 = min((r for r in station_rows if "E10" in r["prices"]),
                       key=lambda r: r["prices"]["E10"], default=None)
    cheapest_e10_answer = (
        f"The cheapest unleaded petrol in the UK right now is {cheapest_e10['prices']['E10']:.1f}p "
        f"per litre at {cheapest_e10['name']}."
        if cheapest_e10 else "Check the table above for current prices."
    )

    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "How often are UK fuel prices updated?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Prices are updated every 4 hours using data from the GOV.UK Fuel Finder. Stations report price changes within 30 minutes of changes at the pump.",
                },
            },
            {
                "@type": "Question",
                "name": "What is the cheapest petrol in the UK right now?",
                "acceptedAnswer": {"@type": "Answer", "text": cheapest_e10_answer},
            },
            {
                "@type": "Question",
                "name": "How many petrol stations are tracked?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": f"This page tracks fuel prices at {len(station_rows):,} petrol stations across the UK, covering all major brands and independent retailers.",
                },
            },
        ],
    }

    schema_tags = (
        '<script type="application/ld+json">'
        + json.dumps(dataset_schema, separators=(",", ":"))
        + "</script>\n"
        + '<script type="application/ld+json">'
        + json.dumps(faq_schema, separators=(",", ":"))
        + "</script>"
    )

    return {
        "html": "\n".join(parts),
        "codeinjection_head": _PAGE_CSS + "\n" + schema_tags,
        "codeinjection_foot": _PAGE_JS,
        "station_json": json.dumps(json_data, separators=(",", ":")),
    }


# Keep backward-compatible function name
def generate_html(
    stations: list[Station],
    regions: list[RegionConfig],
    fuel_types: list[str],
) -> str:
    """Generate HTML content for the Ghost fuel prices page."""
    return generate_page_data(stations, regions, fuel_types)["html"]


def upload_station_data(ghost_host: str, json_str: str):
    """Upload station JSON data to Ghost's static files directory via SSH."""
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=True) as f:
        f.write(json_str)
        f.flush()
        result = subprocess.run(
            [
                "scp", "-o", "StrictHostKeyChecking=no",
                f.name, f"root@{ghost_host}:/var/www/ghost/content/files/stations.json",
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"SCP failed: {result.stderr}")

    # Fix ownership
    subprocess.run(
        ["ssh", "-o", "StrictHostKeyChecking=no", f"root@{ghost_host}",
         "chown ghost:ghost /var/www/ghost/content/files/stations.json"],
        capture_output=True, text=True, timeout=10,
    )
    logger.info("Uploaded station data to Ghost (%d bytes)", len(json_str))


async def update_ghost_page(
    ghost_url: str,
    admin_api_key: str,
    page_slug: str,
    html_content: str,
    page_id: str = "",
    codeinjection_head: str = "",
    codeinjection_foot: str = "",
):
    """Update a Ghost page with fuel price data."""
    token = _build_token(admin_api_key)
    headers = {
        "Authorization": f"Ghost {token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        # Get page by ID or slug
        if page_id:
            url = f"{ghost_url}/ghost/api/admin/pages/{page_id}/?source=html"
        else:
            url = f"{ghost_url}/ghost/api/admin/pages/slug/{page_slug}/?source=html"

        resp = await client.get(url, headers=headers)
        resp.raise_for_status()

        page = resp.json()["pages"][0]
        pid = page["id"]
        updated_at = page["updated_at"]

        page_data = {
            "html": html_content,
            "updated_at": updated_at,
        }
        if codeinjection_head:
            page_data["codeinjection_head"] = codeinjection_head
        if codeinjection_foot:
            page_data["codeinjection_foot"] = codeinjection_foot

        resp = await client.put(
            f"{ghost_url}/ghost/api/admin/pages/{pid}/?source=html",
            headers=headers,
            json={
                "pages": [page_data]
            },
        )
        resp.raise_for_status()
        logger.info("Updated Ghost page: %s", page_slug)
