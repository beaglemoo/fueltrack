"""Ghost page publisher - updates fuel prices page on sillymoo.dev."""

import html
import json
import logging
import time
from datetime import datetime, timezone

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


_PAGE_CSS = """
<style>
.ft-search-wrap{margin:0 0 1.5em;position:sticky;top:0;z-index:10;background:var(--ghost-accent-color,#1a1a2e);padding:1em;border-radius:8px}
.ft-search{width:100%;padding:12px 16px;font-size:1.1em;border:2px solid rgba(255,255,255,0.2);border-radius:6px;background:rgba(255,255,255,0.1);color:#fff;outline:none;box-sizing:border-box}
.ft-search::placeholder{color:rgba(255,255,255,0.5)}
.ft-search:focus{border-color:rgba(255,255,255,0.5)}
.ft-meta{display:flex;justify-content:space-between;align-items:center;margin-top:8px;font-size:0.85em;color:rgba(255,255,255,0.7);flex-wrap:wrap;gap:8px}
.ft-sort{display:flex;gap:4px;flex-wrap:wrap}
.ft-sort button{background:rgba(255,255,255,0.15);border:none;color:#fff;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:0.85em}
.ft-sort button.active{background:rgba(255,255,255,0.35)}
.ft-results{margin:1em 0}
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
@media(max-width:600px){
.ft-results .hide-mobile{display:none}
.ft-results td,.ft-results th{padding:4px 3px;font-size:0.8em}
}
</style>
"""

_PAGE_JS = """
<script>
(function(){
var S=window._FT_DATA||[];
var input=document.getElementById('ft-search');
var tbody=document.getElementById('ft-body');
var countEl=document.getElementById('ft-count');
var moreBtn=document.getElementById('ft-more');
var promptEl=document.getElementById('ft-prompt');
var sortBtns=document.querySelectorAll('.ft-sort button');
var filtered=[];
var limit=100;
var sortCol='e';
var sortAsc=true;
var timer=null;

function fmt(v){if(v==null)return'-';return v<10?v+'p':v.toFixed(1)+'p';}

function render(){
  var frag=document.createDocumentFragment();
  var show=filtered.slice(0,limit);
  tbody.textContent='';
  for(var i=0;i<show.length;i++){
    var s=show[i];
    var tr=document.createElement('tr');
    var c=function(t,cls){var td=document.createElement('td');td.textContent=t;if(cls)td.className=cls;return td;};
    var nameCell=document.createElement('td');
    var nameText=document.createTextNode(s.n);
    nameCell.appendChild(nameText);
    if(s.l&&s.l!==s.n){var loc=document.createElement('span');loc.className='ft-loc';loc.textContent=s.l;nameCell.appendChild(loc);}
    tr.appendChild(nameCell);
    tr.appendChild(c(s.b,''));
    tr.appendChild(c(fmt(s.e),'price'+(s._ce?' cheap':'')));
    tr.appendChild(c(fmt(s.s),'price hide-mobile'));
    tr.appendChild(c(fmt(s.d),'price'+(s._cd?' cheap':'')));
    tr.appendChild(c(fmt(s.p),'price hide-mobile'));
    frag.appendChild(tr);
  }
  tbody.appendChild(frag);
  countEl.textContent=filtered.length===S.length?filtered.length.toLocaleString()+' stations':filtered.length.toLocaleString()+' matches';
  moreBtn.style.display=filtered.length>limit?'block':'none';
  if(filtered.length>limit)moreBtn.textContent='Show more ('+Math.min(100,filtered.length-limit)+' of '+(filtered.length-limit)+' remaining)';
  promptEl.style.display=filtered.length===0&&input.value.length===0?'block':'none';
}

function doSort(){
  var col=sortCol;
  filtered.sort(function(a,b){
    var va=a[col],vb=b[col];
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
  if(q===''){
    filtered=S.slice();
  }else{
    var terms=q.split(/\\s+/);
    filtered=S.filter(function(s){
      var hay=(s.n+'|'+s.b+'|'+(s.l||'')).toLowerCase();
      return terms.every(function(t){return hay.indexOf(t)>=0;});
    });
  }
  doSort();
  markCheapest();
  render();
}

input.addEventListener('input',function(){
  clearTimeout(timer);
  timer=setTimeout(filter,200);
});

moreBtn.addEventListener('click',function(){
  limit+=100;
  render();
});

sortBtns.forEach(function(btn){
  btn.addEventListener('click',function(){
    var col=this.getAttribute('data-col');
    if(sortCol===col){sortAsc=!sortAsc;}else{sortCol=col;sortAsc=col==='n'||col==='b';}
    sortBtns.forEach(function(b){b.classList.remove('active');});
    this.classList.add('active');
    doSort();
    render();
  });
});

// Initial render - show prompt
promptEl.style.display='block';
countEl.textContent=S.length.toLocaleString()+' stations';
})();
</script>
"""


def generate_html(
    stations: list[Station],
    regions: list[RegionConfig],
    fuel_types: list[str],
) -> str:
    """Generate HTML content for the Ghost fuel prices page."""
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

        station_rows.append({
            "name": s.trading_name,
            "brand": brand,
            "location": location,
            "region": region,
            "prices": valid_prices,
        })

    # Sort by cheapest E10, then B7_STANDARD
    def sort_key(s):
        return s["prices"].get("E10", s["prices"].get("B7_STANDARD", 999))

    station_rows.sort(key=sort_key)

    # Build compact JSON data for client-side search
    json_data = []
    for row in station_rows:
        json_data.append({
            "n": row["name"],
            "b": row["brand"],
            "l": row["location"],
            "e": row["prices"].get("E10"),
            "s": row["prices"].get("E5"),
            "d": row["prices"].get("B7_STANDARD"),
            "p": row["prices"].get("B7_PREMIUM"),
        })

    # Build HTML
    parts = []

    # CSS
    parts.append(_PAGE_CSS)

    # Header
    parts.append(f'<p><strong>Last updated:</strong> {now}</p>')
    parts.append(f'<p><strong>{len(station_rows):,} stations</strong> reporting prices across the UK. '
                 'Data from the <a href="https://www.fuel-finder.service.gov.uk/">GOV.UK Fuel Finder</a>. '
                 'Prices update within 30 minutes of changes at the pump. '
                 'This page refreshes every 4 hours.</p>')

    # Search UI
    parts.append('<div class="ft-search-wrap">')
    parts.append('<input type="text" id="ft-search" class="ft-search" '
                 'placeholder="Search by station name, brand, or location..." autocomplete="off">')
    parts.append('<div class="ft-meta">')
    parts.append('<span id="ft-count"></span>')
    parts.append('<div class="ft-sort">Sort: '
                 '<button data-col="e" class="active">Unleaded</button>'
                 '<button data-col="d">Diesel</button>'
                 '<button data-col="s">Super</button>'
                 '<button data-col="n">Name</button>'
                 '</div>')
    parts.append('</div>')
    parts.append('</div>')

    # Results area
    parts.append('<div class="ft-results">')
    parts.append('<div id="ft-prompt" class="ft-prompt">Type a location, station name, or brand to search all UK fuel prices</div>')
    parts.append('<table>')
    parts.append('<thead><tr>'
                 '<th>Station</th><th>Brand</th>'
                 '<th>Unleaded</th><th class="hide-mobile">Super</th>'
                 '<th>Diesel</th><th class="hide-mobile">Premium</th>'
                 '</tr></thead>')
    parts.append('<tbody id="ft-body"></tbody>')
    parts.append('</table>')
    parts.append('<button id="ft-more" class="ft-more" style="display:none">Show more</button>')
    parts.append('</div>')

    parts.append('<hr>')

    # Regional summaries (static HTML)
    for region in regions:
        region_stations = [s for s in station_rows if s["region"] == region.name]
        if not region_stations:
            continue

        parts.append(f'<h2>{_esc(region.label)}</h2>')

        for ft in ["E10", "E5", "B7_STANDARD", "B7_PREMIUM"]:
            ft_label = {"E10": "Unleaded (E10)", "E5": "Super Unleaded (E5)",
                        "B7_STANDARD": "Diesel", "B7_PREMIUM": "Premium Diesel"}.get(ft, ft)
            stations_with_ft = [(s, s["prices"][ft]) for s in region_stations if ft in s["prices"]]
            if not stations_with_ft:
                continue
            stations_with_ft.sort(key=lambda x: x[1])
            cheapest = stations_with_ft[0]
            parts.append(
                f'<p><strong>Cheapest {ft_label}:</strong> {cheapest[1]:.1f}p - {_esc(cheapest[0]["name"])}</p>'
            )

        parts.append('<table>')
        parts.append('<thead><tr>'
                     '<th>Station</th><th>Brand</th>'
                     '<th>Unleaded</th><th>Super</th>'
                     '<th>Diesel</th><th>Premium</th>'
                     '</tr></thead>')
        parts.append('<tbody>')

        for s in region_stations:
            parts.append(
                f'<tr>'
                f'<td>{_esc(s["name"])}</td>'
                f'<td>{_esc(s["brand"])}</td>'
                f'<td>{_format_price(s["prices"].get("E10"))}</td>'
                f'<td>{_format_price(s["prices"].get("E5"))}</td>'
                f'<td>{_format_price(s["prices"].get("B7_STANDARD"))}</td>'
                f'<td>{_format_price(s["prices"].get("B7_PREMIUM"))}</td>'
                f'</tr>'
            )

        parts.append('</tbody></table>')

    # National top 20 cheapest
    parts.append('<hr>')
    parts.append('<h2>UK Top 20 Cheapest - Unleaded (E10)</h2>')
    parts.append('<table>')
    parts.append('<thead><tr><th>#</th><th>Station</th><th>Brand</th><th>Price</th></tr></thead>')
    parts.append('<tbody>')
    e10_sorted = [(s, s["prices"]["E10"]) for s in station_rows if "E10" in s["prices"]]
    e10_sorted.sort(key=lambda x: x[1])
    for i, (s, price) in enumerate(e10_sorted[:20], 1):
        parts.append(f'<tr><td>{i}</td><td>{_esc(s["name"])}</td><td>{_esc(s["brand"])}</td><td>{price:.1f}p</td></tr>')
    parts.append('</tbody></table>')

    parts.append('<h2>UK Top 20 Cheapest - Diesel (B7)</h2>')
    parts.append('<table>')
    parts.append('<thead><tr><th>#</th><th>Station</th><th>Brand</th><th>Price</th></tr></thead>')
    parts.append('<tbody>')
    b7_sorted = [(s, s["prices"]["B7_STANDARD"]) for s in station_rows if "B7_STANDARD" in s["prices"]]
    b7_sorted.sort(key=lambda x: x[1])
    for i, (s, price) in enumerate(b7_sorted[:20], 1):
        parts.append(f'<tr><td>{i}</td><td>{_esc(s["name"])}</td><td>{_esc(s["brand"])}</td><td>{price:.1f}p</td></tr>')
    parts.append('</tbody></table>')

    # Footer
    parts.append('<hr>')
    parts.append('<p><small>Powered by <a href="https://github.com/beaglemoo/fueltrack">FuelTrack</a> '
                 '| Data: GOV.UK Fuel Finder (Open Government Licence v3.0) '
                 '| Updates every 4 hours</small></p>')

    # Embed JSON data and JS at the end
    parts.append(f'<script>window._FT_DATA={json.dumps(json_data, separators=(",",":"))};</script>')
    parts.append(_PAGE_JS)

    return "\n".join(parts)


async def update_ghost_page(
    ghost_url: str,
    admin_api_key: str,
    page_slug: str,
    html_content: str,
    page_id: str = "",
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

        resp = await client.put(
            f"{ghost_url}/ghost/api/admin/pages/{pid}/?source=html",
            headers=headers,
            json={
                "pages": [{
                    "html": html_content,
                    "updated_at": updated_at,
                }]
            },
        )
        resp.raise_for_status()
        logger.info("Updated Ghost page: %s", page_slug)
