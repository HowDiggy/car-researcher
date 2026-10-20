import html
import urllib.parse
from typing import List, Dict, Any, Optional
from src.config.settings import settings


def _esc(val: Any) -> str:
    if val is None:
        return ""
    return html.escape(str(val))


def _score_badge_classes(score: float) -> str:
    if score >= 85.0:
        return "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
    elif score >= 75.0:
        return "bg-sky-500/20 text-sky-300 border-sky-500/40"
    elif score >= 60.0:
        return "bg-amber-500/20 text-amber-300 border-amber-500/40"
    return "bg-rose-500/20 text-rose-300 border-rose-500/40"


def render_kpis_partial(kpis: Dict[str, Any]) -> str:
    """Render the top 4 KPI telemetry cards."""
    return f"""
    <div id="kpi-bar" class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div class="bg-slate-900/90 border border-slate-800 rounded-xl p-4 shadow-lg">
            <div class="text-xs font-medium uppercase tracking-wider text-slate-400">Active Bay Area Inventory</div>
            <div class="mt-1 flex items-baseline justify-between">
                <span class="text-2xl font-bold text-white">{kpis['total_active']}</span>
                <span class="text-xs text-slate-400">Within {settings.search_radius_miles}mi of {settings.search_zip_code}</span>
            </div>
        </div>
        <div class="bg-slate-900/90 border border-emerald-900/50 rounded-xl p-4 shadow-lg">
            <div class="text-xs font-medium uppercase tracking-wider text-emerald-400">Excellent Deals (Score &ge; 85)</div>
            <div class="mt-1 flex items-baseline justify-between">
                <span class="text-2xl font-bold text-emerald-300">{kpis['excellent_count']}</span>
                <span class="text-xs text-emerald-400/80">High-conviction targets</span>
            </div>
        </div>
        <div class="bg-slate-900/90 border border-slate-800 rounded-xl p-4 shadow-lg">
            <div class="text-xs font-medium uppercase tracking-wider text-slate-400">Max Below-Market Savings</div>
            <div class="mt-1 flex items-baseline justify-between">
                <span class="text-2xl font-bold text-teal-300">-${kpis['max_savings']:,}</span>
                <span class="text-xs text-slate-400">Avg discount: -${kpis['avg_discount']:,}</span>
            </div>
        </div>
        <div class="bg-slate-900/90 border border-slate-800 rounded-xl p-4 shadow-lg">
            <div class="text-xs font-medium uppercase tracking-wider text-slate-400">Saved &amp; Price Drops</div>
            <div class="mt-1 flex items-baseline justify-between">
                <span class="text-2xl font-bold text-amber-300">&#9733; {kpis['saved_count']}</span>
                <span class="text-xs text-sky-400">&#8595; {kpis['price_drops_count']} price drops</span>
            </div>
        </div>
    </div>
    """


def render_deals_section(
    deals: List[Dict[str, Any]],
    kpis: Dict[str, Any],
    filters: Dict[str, Any],
) -> str:
    """Render both KPI summary and the filtered deals Grid or Table view."""
    view_mode = filters.get("view", "grid")
    tab = filters.get("tab", "all")

    # Build query string for export links
    export_params = {
        k: v for k, v in filters.items()
        if v is not None and v != "" and k != "view"
    }
    export_qs = urllib.parse.urlencode(export_params)

    tabs_meta = [
        ("all", f"All Active ({kpis['total_active']})"),
        ("excellent", f"🔥 Excellent ≥85 ({kpis['excellent_count']})"),
        ("good", "✨ Good Value ≥75"),
        ("drops", f"📉 Price Drops ({kpis['price_drops_count']})"),
        ("saved", f"⭐ Saved ({kpis['saved_count']})"),
        ("dismissed", f"👁️ Dismissed ({kpis['dismissed_count']})"),
    ]
    tabs_html = []
    for t_key, t_label in tabs_meta:
        active_cls = (
            "bg-indigo-600 text-white border-indigo-500 shadow"
            if tab == t_key
            else "bg-slate-800/80 text-slate-300 border-slate-700 hover:bg-slate-700"
        )
        tabs_html.append(
            f'<button type="button" onclick="setFilterTab(\'{t_key}\')" '
            f'class="px-3 py-1.5 rounded-lg text-xs font-medium border transition {active_cls}">'
            f'{t_label}</button>'
        )

    if not deals:
        content_html = """
        <div class="bg-slate-900/70 border border-slate-800 rounded-2xl p-12 text-center my-4">
            <div class="text-4xl mb-3">🔍</div>
            <h3 class="text-lg font-semibold text-white">No matching vehicles found</h3>
            <p class="text-sm text-slate-400 mt-1 max-w-md mx-auto">
                Try relaxing your price, mileage, or make filters—or click <strong>Scan Marketplace</strong> in the top bar to scrape fresh Bay Area inventory for a new model.
            </p>
        </div>
        """
    elif view_mode == "table":
        content_html = _render_table_view(deals)
    else:
        content_html = _render_grid_view(deals)

    return f"""
    {render_kpis_partial(kpis)}

    <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div class="flex flex-wrap items-center gap-1.5">
            {''.join(tabs_html)}
        </div>
        <div class="flex items-center gap-2">
            <span class="text-xs text-slate-400 mr-1">Showing <strong class="text-white">{len(deals)}</strong> vehicles</span>
            <a href="/api/export/csv?{export_qs}"
               class="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition">
               ⬇️ Export CSV
            </a>
            <a href="/api/export/markdown?{export_qs}" target="_blank"
               class="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition">
               📝 Export Markdown
            </a>
        </div>
    </div>

    {content_html}
    """


def _render_grid_view(deals: List[Dict[str, Any]]) -> str:
    cards: List[str] = []
    for idx, d in enumerate(deals, 1):
        lid = _esc(d["id"])
        title = _esc(d["title"])
        url = _esc(d["url"])
        vin = _esc(d["vin"])
        price = d["price"]
        fmv = d["market_value"]
        delta = d["price_delta"]
        pct = d["pct_savings"]
        score = d["deal_score"]
        rec = _esc(d["recommendation"].replace("_", " "))
        mileage = d["mileage"]
        city = _esc(d["location_city"])
        dist_str = f"{d['distance_miles']:.1f} mi • {city}" if d["distance_miles"] is not None else city
        dealer = _esc(d["seller_name"])
        color = _esc(d["exterior_color"])
        title_status = _esc(d["title_status"])
        make_q = urllib.parse.quote(str(d["make"]))
        model_q = urllib.parse.quote(str(d["model"]))
        year_q = int(d["year"])

        badge_cls = _score_badge_classes(score)
        if delta < 0:
            delta_pill = f'<span class="text-emerald-400 font-semibold">-${abs(delta):,} ({pct}%) vs FMV</span>'
        else:
            delta_pill = f'<span class="text-amber-400 font-semibold">+${delta:,} (+{pct}%) vs FMV</span>'

        price_drop_badge = ""
        if d["price_change"] < 0:
            price_drop_badge = (
                f'<span class="px-2 py-0.5 text-[11px] font-semibold rounded bg-sky-500/20 text-sky-300 border border-sky-500/40">'
                f'📉 Price Drop -${abs(d["price_change"]):,}</span>'
            )

        cpo_badge = (
            '<span class="px-2 py-0.5 text-[11px] font-semibold rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/40">CPO</span>'
            if d.get("cpo") else ""
        )

        thumb_url = d.get("thumbnail")
        if thumb_url:
            img_html = f'<img src="{_esc(thumb_url)}" alt="{title}" loading="lazy" class="w-full h-44 object-cover group-hover:scale-105 transition duration-300" />'
        else:
            img_html = (
                '<div class="w-full h-44 bg-gradient-to-br from-slate-800 to-slate-900 flex items-center justify-center text-slate-600">'
                '<span class="text-4xl">⚡</span></div>'
            )

        bd = d["score_breakdown"]
        star_cls = "text-amber-400 bg-amber-500/20 border-amber-500/40" if d["is_bookmarked"] else "text-slate-400 bg-slate-800 border-slate-700 hover:text-amber-300"
        star_label = "★ Saved" if d["is_bookmarked"] else "☆ Save"
        dismiss_label = "Restore" if d["is_dismissed"] else "Hide"

        cards.append(f"""
        <div class="group bg-slate-900/95 border border-slate-800 hover:border-slate-700 rounded-2xl overflow-hidden shadow-lg flex flex-col justify-between transition">
            <div>
                <div class="relative overflow-hidden bg-slate-950">
                    {img_html}
                    <div class="absolute top-2.5 left-2.5 flex items-center gap-1.5">
                        <span class="px-2 py-0.5 text-xs font-bold rounded-md bg-slate-950/85 text-slate-200 border border-slate-700">#{idx}</span>
                        {cpo_badge}
                        {price_drop_badge}
                    </div>
                    <div class="absolute top-2.5 right-2.5">
                        <span class="px-2.5 py-1 text-xs font-bold rounded-lg border backdrop-blur-md {badge_cls}">
                            {score} • {rec}
                        </span>
                    </div>
                </div>

                <div class="p-4">
                    <div class="flex items-start justify-between gap-2">
                        <a href="{url}" target="_blank" rel="noopener"
                           class="text-base font-bold text-white hover:text-indigo-400 transition line-clamp-1" title="{title}">
                            {title}
                        </a>
                    </div>

                    <div class="mt-2 flex items-baseline justify-between border-b border-slate-800/80 pb-3">
                        <div>
                            <span class="text-2xl font-extrabold text-white">${price:,}</span>
                            <span class="text-xs text-slate-400 ml-1.5">FMV: ${fmv:,}</span>
                        </div>
                        <div class="text-xs text-right">
                            {delta_pill}
                        </div>
                    </div>

                    <!-- 4-Factor Mini Breakdown -->
                    <div class="grid grid-cols-4 gap-2 my-3 text-[11px]">
                        <div>
                            <div class="flex justify-between text-slate-400"><span>Price</span><span class="text-slate-200">{bd['price_score']:.0f}</span></div>
                            <div class="h-1 bg-slate-800 rounded mt-0.5 overflow-hidden"><div class="h-full bg-emerald-500" style="width:{min(100, int(bd['price_score']))}%"></div></div>
                        </div>
                        <div>
                            <div class="flex justify-between text-slate-400"><span>Hist</span><span class="text-slate-200">{bd['history_score']:.0f}</span></div>
                            <div class="h-1 bg-slate-800 rounded mt-0.5 overflow-hidden"><div class="h-full bg-sky-500" style="width:{min(100, int(bd['history_score']))}%"></div></div>
                        </div>
                        <div>
                            <div class="flex justify-between text-slate-400"><span>DOM</span><span class="text-slate-200">{bd['leverage_score']:.0f}</span></div>
                            <div class="h-1 bg-slate-800 rounded mt-0.5 overflow-hidden"><div class="h-full bg-indigo-500" style="width:{min(100, int(bd['leverage_score']))}%"></div></div>
                        </div>
                        <div>
                            <div class="flex justify-between text-slate-400"><span>Prox</span><span class="text-slate-200">{bd['proximity_score']:.0f}</span></div>
                            <div class="h-1 bg-slate-800 rounded mt-0.5 overflow-hidden"><div class="h-full bg-teal-500" style="width:{min(100, int(bd['proximity_score']))}%"></div></div>
                        </div>
                    </div>

                    <div class="space-y-1 text-xs text-slate-300 mt-2">
                        <div class="flex justify-between">
                            <span class="text-slate-400">Odometer &amp; Title:</span>
                            <span class="font-medium">{mileage:,} mi • <span class="text-emerald-400">{title_status}</span></span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-slate-400">Location:</span>
                            <span class="font-medium truncate max-w-[180px]" title="{dist_str}">{dist_str}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-slate-400">Dealer:</span>
                            <span class="font-medium truncate max-w-[180px]" title="{dealer}">{dealer}</span>
                        </div>
                        <div class="flex justify-between items-center pt-1">
                            <span class="text-slate-400">VIN ({color}):</span>
                            <button type="button" onclick="navigator.clipboard.writeText('{vin}'); this.innerText='Copied!'; setTimeout(()=>this.innerText='{vin}', 1200);"
                                    class="font-mono text-[11px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 hover:bg-slate-700 border border-slate-700"
                                    title="Click to copy VIN">
                                {vin}
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <div class="px-4 py-2.5 bg-slate-950/70 border-t border-slate-800/80 flex items-center justify-between gap-1.5 text-xs">
                <div class="flex items-center gap-1">
                    <button type="button"
                            hx-post="/api/listing/{lid}/bookmark"
                            hx-target="#deals-container"
                            hx-include="#filter-form"
                            class="px-2 py-1 rounded border text-[11px] font-medium transition {star_cls}">
                        {star_label}
                    </button>
                    <button type="button"
                            hx-post="/api/listing/{lid}/dismiss"
                            hx-target="#deals-container"
                            hx-include="#filter-form"
                            class="px-2 py-1 rounded border border-slate-700 bg-slate-800/80 text-slate-400 hover:text-rose-300 text-[11px] transition">
                        {dismiss_label}
                    </button>
                </div>
                <div class="flex items-center gap-1">
                    <button type="button"
                            hx-get="/partials/listing/{lid}/history"
                            hx-target="#modal-body"
                            onclick="openModal()"
                            class="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-[11px] transition"
                            title="View TimescaleDB Price Snapshots & Score Breakdown">
                        📈 History
                    </button>
                    <button type="button"
                            hx-get="/partials/model-profile?make={make_q}&model={model_q}&year={year_q}"
                            hx-target="#modal-body"
                            onclick="openModal()"
                            class="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-[11px] transition"
                            title="View NHTSA Recalls, Complaints & EPA Range">
                        🛡️ NHTSA/EPA
                    </button>
                    <a href="{url}" target="_blank" rel="noopener"
                       class="px-2.5 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-[11px] transition">
                        View ↗
                    </a>
                </div>
            </div>
        </div>
        """)

    return f'<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">{"".join(cards)}</div>'


def _render_table_view(deals: List[Dict[str, Any]]) -> str:
    rows: List[str] = []
    for idx, d in enumerate(deals, 1):
        lid = _esc(d["id"])
        title = _esc(d["title"])
        url = _esc(d["url"])
        vin = _esc(d["vin"])
        price = d["price"]
        fmv = d["market_value"]
        delta = d["price_delta"]
        pct = d["pct_savings"]
        score = d["deal_score"]
        mileage = d["mileage"]
        city = _esc(d["location_city"])
        dist_str = f"{d['distance_miles']:.1f} mi ({city})" if d["distance_miles"] is not None else city
        dealer = _esc(d["seller_name"])
        badge_cls = _score_badge_classes(score)
        make_q = urllib.parse.quote(str(d["make"]))
        model_q = urllib.parse.quote(str(d["model"]))
        year_q = int(d["year"])

        delta_str = f"-${abs(delta):,} ({pct}%)" if delta < 0 else f"+${delta:,} (+{pct}%)"
        delta_cls = "text-emerald-400 font-semibold" if delta < 0 else "text-amber-400"
        star_icon = "★" if d["is_bookmarked"] else "☆"
        star_cls = "text-amber-400" if d["is_bookmarked"] else "text-slate-500 hover:text-amber-300"

        rows.append(f"""
        <tr class="border-b border-slate-800/80 hover:bg-slate-800/40 transition text-xs">
            <td class="py-3 px-3 font-mono text-slate-400">#{idx}</td>
            <td class="py-3 px-3">
                <span class="px-2 py-0.5 font-bold rounded border {badge_cls}">{score}</span>
            </td>
            <td class="py-3 px-3">
                <a href="{url}" target="_blank" rel="noopener" class="font-semibold text-white hover:text-indigo-400">{title}</a>
                <div class="text-[11px] text-slate-400 font-mono">{vin} • {_esc(d['exterior_color'])}</div>
            </td>
            <td class="py-3 px-3 font-bold text-white">${price:,}</td>
            <td class="py-3 px-3 text-slate-300">${fmv:,}</td>
            <td class="py-3 px-3 {delta_cls}">{delta_str}</td>
            <td class="py-3 px-3 text-slate-200">{mileage:,} mi</td>
            <td class="py-3 px-3 text-slate-300">{dist_str}</td>
            <td class="py-3 px-3 text-slate-300 truncate max-w-[160px]" title="{dealer}">{dealer}</td>
            <td class="py-3 px-3 text-right whitespace-nowrap space-x-1">
                <button type="button" hx-post="/api/listing/{lid}/bookmark" hx-target="#deals-container" hx-include="#filter-form"
                        class="px-1.5 py-1 text-sm {star_cls}" title="Toggle Bookmark">{star_icon}</button>
                <button type="button" hx-get="/partials/listing/{lid}/history" hx-target="#modal-body" onclick="openModal()"
                        class="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700">📈</button>
                <button type="button" hx-get="/partials/model-profile?make={make_q}&model={model_q}&year={year_q}" hx-target="#modal-body" onclick="openModal()"
                        class="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700">🛡️</button>
                <button type="button" hx-post="/api/listing/{lid}/dismiss" hx-target="#deals-container" hx-include="#filter-form"
                        class="px-2 py-1 rounded bg-slate-800 hover:bg-rose-900/50 text-slate-400 hover:text-rose-200 border border-slate-700">✕</button>
                <a href="{url}" target="_blank" rel="noopener"
                   class="px-2.5 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white font-medium">View ↗</a>
            </td>
        </tr>
        """)

    return f"""
    <div class="bg-slate-900/95 border border-slate-800 rounded-2xl overflow-x-auto shadow-lg">
        <table class="w-full text-left border-collapse">
            <thead>
                <tr class="border-b border-slate-800 text-[11px] uppercase tracking-wider text-slate-400 bg-slate-950/60">
                    <th class="py-3 px-3">#</th>
                    <th class="py-3 px-3">Score</th>
                    <th class="py-3 px-3">Vehicle &amp; VIN</th>
                    <th class="py-3 px-3">Price</th>
                    <th class="py-3 px-3">Est. FMV</th>
                    <th class="py-3 px-3">Savings vs FMV</th>
                    <th class="py-3 px-3">Mileage</th>
                    <th class="py-3 px-3">Proximity</th>
                    <th class="py-3 px-3">Dealer</th>
                    <th class="py-3 px-3 text-right">Actions</th>
                </tr>
            </thead>
            <tbody>
                {"".join(rows)}
            </tbody>
        </table>
    </div>
    """


def render_listing_history_modal(history_data: Optional[Dict[str, Any]]) -> str:
    """Render the TimescaleDB price history and 4-factor deal score breakdown modal."""
    if not history_data:
        return '<div class="p-6 text-slate-300">Listing not found.</div>'

    d = history_data["deal"]
    snapshots = history_data["snapshots"]
    bd = d["score_breakdown"]

    snap_rows = []
    for s in snapshots:
        chg = s["price_change"]
        if chg < 0:
            chg_badge = f'<span class="text-emerald-400 font-semibold">-${abs(chg):,}</span>'
        elif chg > 0:
            chg_badge = f'<span class="text-rose-400">+${chg:,}</span>'
        else:
            chg_badge = '<span class="text-slate-500">No change</span>'

        snap_rows.append(f"""
        <tr class="border-b border-slate-800/70 text-xs">
            <td class="py-2 px-3 font-mono text-slate-300">{_esc(s['time'])}</td>
            <td class="py-2 px-3 font-bold text-white">${s['price']:,}</td>
            <td class="py-2 px-3">{chg_badge}</td>
            <td class="py-2 px-3 text-slate-300">{s['days_on_market']} days</td>
        </tr>
        """)

    return f"""
    <div class="p-6">
        <div class="flex items-start justify-between gap-4 border-b border-slate-800 pb-4">
            <div>
                <span class="text-xs font-mono uppercase text-indigo-400">{_esc(d['platform'])} • VIN: {_esc(d['vin'])}</span>
                <h2 class="text-xl font-bold text-white mt-0.5">{_esc(d['title'])}</h2>
                <p class="text-xs text-slate-400 mt-1">{_esc(d['seller_name'])} • {_esc(d['location_city'])}</p>
            </div>
            <div class="text-right">
                <div class="text-2xl font-extrabold text-white">${d['price']:,}</div>
                <div class="text-xs text-emerald-400">Est. Fair Value: ${d['market_value']:,}</div>
            </div>
        </div>

        <div class="mt-5">
            <h3 class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
                Composite Deal Score Breakdown ({d['deal_score']} / 100 — {_esc(d['recommendation'])})
            </h3>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs bg-slate-950/60 p-4 rounded-xl border border-slate-800">
                <div>
                    <div class="flex justify-between mb-1">
                        <span class="text-slate-300">1. Price vs. Market Value (50% weight)</span>
                        <span class="font-bold text-emerald-400">{bd['price_score']:.1f} / 100</span>
                    </div>
                    <div class="h-2 bg-slate-800 rounded overflow-hidden"><div class="h-full bg-emerald-500" style="width:{min(100, int(bd['price_score']))}%"></div></div>
                </div>
                <div>
                    <div class="flex justify-between mb-1">
                        <span class="text-slate-300">2. Title &amp; Accident History (25% weight)</span>
                        <span class="font-bold text-sky-400">{bd['history_score']:.1f} / 100</span>
                    </div>
                    <div class="h-2 bg-slate-800 rounded overflow-hidden"><div class="h-full bg-sky-500" style="width:{min(100, int(bd['history_score']))}%"></div></div>
                </div>
                <div>
                    <div class="flex justify-between mb-1">
                        <span class="text-slate-300">3. Days on Market Leverage (15% weight)</span>
                        <span class="font-bold text-indigo-400">{bd['leverage_score']:.1f} / 100</span>
                    </div>
                    <div class="h-2 bg-slate-800 rounded overflow-hidden"><div class="h-full bg-indigo-500" style="width:{min(100, int(bd['leverage_score']))}%"></div></div>
                </div>
                <div>
                    <div class="flex justify-between mb-1">
                        <span class="text-slate-300">4. Bay Area Proximity (10% weight)</span>
                        <span class="font-bold text-teal-400">{bd['proximity_score']:.1f} / 100</span>
                    </div>
                    <div class="h-2 bg-slate-800 rounded overflow-hidden"><div class="h-full bg-teal-500" style="width:{min(100, int(bd['proximity_score']))}%"></div></div>
                </div>
            </div>
        </div>

        <div class="mt-6">
            <h3 class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                📈 TimescaleDB Price Snapshots ({len(snapshots)} recorded)
            </h3>
            <div class="bg-slate-950/60 border border-slate-800 rounded-xl overflow-hidden">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="border-b border-slate-800 text-[11px] uppercase text-slate-400">
                            <th class="py-2 px-3">Recorded Timestamp</th>
                            <th class="py-2 px-3">Listed Price</th>
                            <th class="py-2 px-3">Price Delta</th>
                            <th class="py-2 px-3">Days on Market</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(snap_rows)}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="mt-6 flex justify-end gap-2">
            <a href="{_esc(d['url'])}" target="_blank" rel="noopener"
               class="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold">
               Open Listing on {_esc(d['platform'])} ↗
            </a>
        </div>
    </div>
    """


def render_model_profile_modal(profile: Dict[str, Any]) -> str:
    """Render the NHTSA Recalls, Consumer Complaints, and EPA Fuel Economy modal."""
    make = _esc(profile.get("make"))
    model = _esc(profile.get("model"))
    year = _esc(profile.get("year"))
    recalls = profile.get("recalls", [])
    complaints = profile.get("complaints", [])
    epa_specs = profile.get("epa_specs", [])

    epa_html = []
    for e in epa_specs:
        epa_html.append(f"""
        <div class="bg-slate-900 border border-slate-800 rounded-lg p-3 text-xs">
            <div class="font-semibold text-white">{year} {make} {model}</div>
            <div class="mt-1 flex items-center justify-between text-slate-300">
                <span>Range: <strong class="text-emerald-400">{e.get('range_miles') or 'N/A'} mi</strong></span>
                <span>Combined: <strong class="text-sky-400">{e.get('comb_mpge') or 'N/A'} MPGe</strong></span>
                <span>Est. Fuel Cost: <strong>${e.get('annual_fuel_cost') or 'N/A'}/yr</strong></span>
            </div>
        </div>
        """)
    if not epa_html:
        epa_html.append('<div class="text-xs text-slate-400 italic">No specific EPA option records returned for this exact model string.</div>')

    recall_items = []
    for r in recalls[:5]:
        recall_items.append(f"""
        <div class="p-3 bg-slate-950/70 border border-rose-900/40 rounded-lg text-xs space-y-1">
            <div class="flex justify-between font-semibold text-rose-300">
                <span>Campaign #{_esc(r.get('campaign_number'))}</span>
                <span>{_esc(r.get('component'))}</span>
            </div>
            <p class="text-slate-300">{_esc(r.get('summary'))}</p>
            <p class="text-slate-400 text-[11px]"><strong>Remedy:</strong> {_esc(r.get('remedy'))}</p>
        </div>
        """)
    if not recall_items:
        recall_items.append('<div class="p-3 bg-emerald-950/30 border border-emerald-800/40 rounded-lg text-xs text-emerald-300">✅ 0 NHTSA safety recalls reported for this model year.</div>')

    complaint_items = []
    for c in complaints[:5]:
        flags = []
        if c.get("crash"):
            flags.append('<span class="text-rose-400 font-bold">💥 Crash</span>')
        if c.get("fire"):
            flags.append('<span class="text-orange-400 font-bold">🔥 Fire</span>')
        flag_str = " • ".join(flags)
        complaint_items.append(f"""
        <div class="p-3 bg-slate-950/70 border border-slate-800 rounded-lg text-xs space-y-1">
            <div class="flex justify-between text-slate-400">
                <span class="font-semibold text-amber-300">{_esc(c.get('component'))}</span>
                <span>ODI #{_esc(c.get('odi_number'))} {flag_str}</span>
            </div>
            <p class="text-slate-300 line-clamp-3">{_esc(c.get('summary'))}</p>
        </div>
        """)
    if not complaint_items:
        complaint_items.append('<div class="text-xs text-slate-400">No NHTSA consumer complaints on file.</div>')

    return f"""
    <div class="p-6 space-y-5 max-h-[80vh] overflow-y-auto">
        <div class="border-b border-slate-800 pb-3 flex items-center justify-between">
            <div>
                <span class="text-xs font-mono uppercase text-indigo-400">Macro Intelligence • Federal Safety &amp; Efficiency</span>
                <h2 class="text-xl font-bold text-white">{year} {make} {model}</h2>
            </div>
            <div class="flex gap-2 text-xs">
                <span class="px-2.5 py-1 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 font-semibold">
                    {profile.get('recalls_count', 0)} Recalls
                </span>
                <span class="px-2.5 py-1 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 font-semibold">
                    {profile.get('complaints_count', 0)} Complaints ({profile.get('fire_count', 0)} Fires)
                </span>
            </div>
        </div>

        <div>
            <h3 class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">⚡ EPA Range &amp; Efficiency Benchmarks</h3>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {"".join(epa_html)}
            </div>
        </div>

        <div>
            <h3 class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">🚨 Official NHTSA Safety Recalls (Top 5)</h3>
            <div class="space-y-2">
                {"".join(recall_items)}
            </div>
        </div>

        <div>
            <h3 class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">📋 Consumer Safety Complaints (NHTSA VOQ Sample)</h3>
            <div class="space-y-2">
                {"".join(complaint_items)}
            </div>
        </div>
    </div>
    """


def render_scan_status_banner(workflow_id: str, summary: Dict[str, Any]) -> str:
    """Render live HTMX polling banner for an active Temporal scan workflow."""
    is_completed = bool(summary.get("is_completed", False))
    scraped = summary.get("total_scraped", 0)
    scored = summary.get("total_scored", 0)
    top_count = summary.get("top_deals_count", 0)

    if is_completed:
        return f"""
        <div class="bg-emerald-950/80 border border-emerald-700/60 text-emerald-200 px-4 py-2.5 rounded-xl mb-5 flex items-center justify-between text-xs shadow-lg"
             hx-get="/partials/deals" hx-target="#deals-container" hx-include="#filter-form" hx-trigger="load">
            <div class="flex items-center gap-2">
                <span class="text-base">✅</span>
                <span><strong>Scan Completed ({_esc(workflow_id)}):</strong> Scraped <strong>{scraped}</strong> listings, scored <strong>{scored}</strong> vehicles, found <strong>{top_count}</strong> top deals! Inventory refreshed below.</span>
            </div>
            <a href="http://localhost:8080/namespaces/default/workflows/{_esc(workflow_id)}" target="_blank"
               class="underline text-emerald-300 hover:text-white font-medium">View in Temporal UI ↗</a>
        </div>
        """

    return f"""
    <div id="active-scan-poller"
         hx-get="/api/scan/{_esc(workflow_id)}/status"
         hx-trigger="every 2s"
         hx-swap="outerHTML"
         class="bg-indigo-950/80 border border-indigo-700/60 text-indigo-200 px-4 py-2.5 rounded-xl mb-5 flex items-center justify-between text-xs shadow-lg animate-pulse">
        <div class="flex items-center gap-2">
            <span class="text-base">⏳</span>
            <span><strong>Temporal Scan Running ({_esc(workflow_id)}):</strong> Scraped <strong>{scraped}</strong> listings • Scored <strong>{scored}</strong> deals so far...</span>
        </div>
        <a href="http://localhost:8080/namespaces/default/workflows/{_esc(workflow_id)}" target="_blank"
           class="underline text-indigo-300 hover:text-white font-medium">Inspect in Temporal UI ↗</a>
    </div>
    """


def render_full_dashboard_page(
    deals: List[Dict[str, Any]],
    kpis: Dict[str, Any],
    filters: Dict[str, Any],
) -> str:
    """Render the full HTML5 Local Web Dashboard."""
    watchlist_options = ['<option value="">All Watchlist Makes &amp; Models</option>']
    scan_options = ['<option value="ALL">All 14 Watchlist EVs (Full Surveillance Run)</option>']
    seen_makes = set()

    for m in settings.search_target_models:
        label = f"{m.make} {m.model}"
        val = f"{m.make} {m.model}"
        sel = "selected" if filters.get("make_filter") == val else ""
        if m.make not in seen_makes:
            seen_makes.add(m.make)
            make_sel = "selected" if filters.get("make_filter") == m.make else ""
            watchlist_options.append(f'<option value="{_esc(m.make)}" {make_sel}>{_esc(m.make)} (All Models)</option>')
        watchlist_options.append(f'<option value="{_esc(val)}" {sel}>&nbsp;&nbsp;↳ {_esc(label)}</option>')
        scan_options.append(f'<option value="{_esc(m.make)}|{_esc(m.model)}">{_esc(label)}</option>')

    deals_section_html = render_deals_section(deals, kpis, filters)

    return f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Bay Area EV Deal Surveillance — Researcher Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@1.9.12"></script>
    <style>
        body {{ background-color: #060913; color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        .line-clamp-1 {{ display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden; }}
        .line-clamp-3 {{ display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }}
    </style>
</head>
<body class="min-h-screen flex flex-col">
    <!-- Top Navigation & Temporal Control Bar -->
    <header class="sticky top-0 z-30 bg-slate-950/90 backdrop-blur-md border-b border-slate-800/80 px-6 py-3.5">
        <div class="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
            <div class="flex items-center gap-3">
                <div class="w-9 h-9 rounded-xl bg-indigo-600 flex items-center justify-center text-lg font-bold shadow-md shadow-indigo-500/20">
                    ⚡
                </div>
                <div>
                    <div class="flex items-center gap-2">
                        <h1 class="text-base font-bold tracking-tight text-white">Bay Area EV Deal Surveillance</h1>
                        <span class="px-2 py-0.5 text-[11px] font-mono rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                            ZIP {settings.search_zip_code} • {settings.search_radius_miles}mi
                        </span>
                    </div>
                    <p class="text-xs text-slate-400">Autonomous Market Valuation • TimescaleDB Price Tracking • NHTSA/EPA Telemetry</p>
                </div>
            </div>

            <!-- Trigger Temporal Workflow Form -->
            <div class="flex items-center gap-2">
                <form hx-post="/api/scan" hx-target="#scan-status-banner" hx-swap="innerHTML" class="flex items-center gap-2">
                    <select name="target" class="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-indigo-500">
                        {"".join(scan_options)}
                    </select>
                    <button type="submit"
                            class="px-3.5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md shadow-indigo-600/20 transition flex items-center gap-1.5">
                        🚀 Scan Marketplace
                    </button>
                </form>
                <a href="http://localhost:8080" target="_blank" rel="noopener"
                   class="px-3 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 text-xs font-medium transition">
                    Temporal UI ↗
                </a>
            </div>
        </div>
    </header>

    <!-- Main Container -->
    <main class="flex-1 max-w-7xl w-full mx-auto px-6 py-6">
        <!-- Dynamic Temporal Scan Banner -->
        <div id="scan-status-banner"></div>

        <!-- Filter & View Control Form -->
        <form id="filter-form"
              hx-get="/partials/deals"
              hx-target="#deals-container"
              hx-trigger="change, keyup delay:300ms from:#search-input, filterChanged"
              class="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 mb-6 shadow-lg">
            <input type="hidden" name="tab" id="tab-input" value="{_esc(filters.get('tab', 'all'))}" />
            <input type="hidden" name="view" id="view-input" value="{_esc(filters.get('view', 'grid'))}" />

            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3">
                <!-- Search Input -->
                <div class="lg:col-span-2">
                    <label class="block text-[11px] font-medium text-slate-400 mb-1">Search Title, Trim, Dealer, City, or VIN</label>
                    <input type="text" id="search-input" name="q" value="{_esc(filters.get('q', ''))}"
                           placeholder="e.g. EQS 580, M50, Walnut Creek, 4MATIC..."
                           class="w-full bg-slate-950 border border-slate-700/80 rounded-lg px-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500" />
                </div>

                <!-- Make / Model Filter -->
                <div>
                    <label class="block text-[11px] font-medium text-slate-400 mb-1">Vehicle Make / Model</label>
                    <select name="make" class="w-full bg-slate-950 border border-slate-700/80 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500">
                        {"".join(watchlist_options)}
                    </select>
                </div>

                <!-- Max Price -->
                <div>
                    <label class="block text-[11px] font-medium text-slate-400 mb-1">Max Price</label>
                    <select name="max_price" class="w-full bg-slate-950 border border-slate-700/80 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500">
                        <option value="">Any Price (&le; $60k)</option>
                        <option value="30000">&le; $30,000</option>
                        <option value="35000">&le; $35,000</option>
                        <option value="40000">&le; $40,000</option>
                        <option value="45000">&le; $45,000</option>
                        <option value="50000">&le; $50,000</option>
                        <option value="55000">&le; $55,000</option>
                    </select>
                </div>

                <!-- Max Mileage -->
                <div>
                    <label class="block text-[11px] font-medium text-slate-400 mb-1">Max Odometer</label>
                    <select name="max_mileage" class="w-full bg-slate-950 border border-slate-700/80 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500">
                        <option value="">Any Mileage</option>
                        <option value="15000">&le; 15,000 miles</option>
                        <option value="25000">&le; 25,000 miles</option>
                        <option value="35000">&le; 35,000 miles</option>
                        <option value="50000">&le; 50,000 miles</option>
                    </select>
                </div>

                <!-- Sort & Layout Toggle -->
                <div>
                    <label class="block text-[11px] font-medium text-slate-400 mb-1">Sort Order &amp; View</label>
                    <div class="flex items-center gap-1.5">
                        <select name="sort" class="flex-1 bg-slate-950 border border-slate-700/80 rounded-lg px-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500">
                            <option value="score_desc">Score (High &rarr; Low)</option>
                            <option value="savings_asc">Savings ($ Below FMV)</option>
                            <option value="price_asc">Price (Low &rarr; High)</option>
                            <option value="mileage_asc">Mileage (Low &rarr; High)</option>
                            <option value="distance_asc">Distance (Closest)</option>
                        </select>
                        <button type="button" onclick="toggleViewMode('grid')" title="Card Grid View"
                                class="px-2 py-1.5 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 text-xs text-slate-200">
                            ⊞
                        </button>
                        <button type="button" onclick="toggleViewMode('table')" title="Compact Table View"
                                class="px-2 py-1.5 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 text-xs text-slate-200">
                            ☰
                        </button>
                    </div>
                </div>
            </div>
        </form>

        <!-- Dynamic Deals Feed Container -->
        <div id="deals-container">
            {deals_section_html}
        </div>
    </main>

    <!-- Reusable Modal Backdrop for Price History & NHTSA/EPA Intelligence -->
    <div id="detail-modal" class="fixed inset-0 z-50 hidden bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
        <div class="bg-slate-900 border border-slate-700 rounded-2xl max-w-2xl w-full shadow-2xl overflow-hidden relative">
            <button type="button" onclick="closeModal()"
                    class="absolute top-3.5 right-4 w-8 h-8 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center justify-center text-sm font-bold">
                ✕
            </button>
            <div id="modal-body">
                <div class="p-8 text-center text-sm text-slate-400">Loading telemetry...</div>
            </div>
        </div>
    </div>

    <script>
        function setFilterTab(tabName) {{
            document.getElementById('tab-input').value = tabName;
            htmx.trigger('#filter-form', 'filterChanged');
        }}
        function toggleViewMode(mode) {{
            document.getElementById('view-input').value = mode;
            htmx.trigger('#filter-form', 'filterChanged');
        }}
        function openModal() {{
            document.getElementById('modal-body').innerHTML = '<div class="p-10 text-center text-sm text-slate-400">Loading live telemetry...</div>';
            document.getElementById('detail-modal').classList.remove('hidden');
        }}
        function closeModal() {{
            document.getElementById('detail-modal').classList.add('hidden');
        }}
        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') closeModal();
        }});
    </script>
</body>
</html>
"""
