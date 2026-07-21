"""Build the production big-screen runtime with non-disruptive data updates.

The original `sc-datav` screen was delivered only as a compiled React asset.
Keeping this tiny, assertion-backed transform beside that asset makes the
otherwise unavoidable compatibility patch reproducible and fails loudly when
the upstream runtime changes.
"""
from __future__ import annotations

from pathlib import Path


ASSET_DIR = Path(__file__).resolve().parent
SOURCE = ASSET_DIR / "index-C5sOsRGW-api-usage-v4.js"
OUTPUT = ASSET_DIR / "index-C5sOsRGW-api-usage-incremental-v1.js"


REPLACEMENTS = {
    # The upper KPI strip is rendered by the compiled React screen.  Keep the
    # 100% NDT metric in that same React data flow (initial load + WebSocket),
    # rather than adding a second request or a DOM clone in the companion
    # script.  That makes the card update atomically with the other KPIs.
    "ns:`repeat(7, 1fr)`,gap:`15px`,width:`100%`}": "ns:`repeat(8, 1fr)`,gap:`15px`,width:`100%`}",
    "{title:`一次探伤合格率`,value:e.once_ndt_pass_rate*100,suffix:`%`,decimals:2,icon:ce,color:`#eab308`,desc:`一次检测合格 / 一次已检数`}": "{title:`一次探伤合格率`,value:e.once_ndt_pass_rate*100,suffix:`%`,decimals:2,icon:ce,color:`#eab308`,desc:`一次检测合格 / 一次已检数`},{title:`100%焊口探伤完成率`,value:e.full_ndt_completion_rate*100,suffix:`%`,decimals:2,icon:ce,color:`#00d6ff`,desc:`X列有效结果 ${e.full_ndt_result_joints||0}/${e.full_ndt_joints||0}道`}",
    "{total_pipelines:0,total_joints:0,completed_welds:0,weld_completion_rate:0,completed_ndt:0,film_approved:0,today_welds:0,today_ndt:0,daily_welding_trend:[],daily_ndt_trend:[],once_ndt_pass_rate:0}": "{total_pipelines:0,total_joints:0,completed_welds:0,weld_completion_rate:0,completed_ndt:0,film_approved:0,today_welds:0,today_ndt:0,daily_welding_trend:[],daily_ndt_trend:[],once_ndt_pass_rate:0,full_ndt_joints:0,full_ndt_result_joints:0,full_ndt_completion_rate:0}",
    # The header glyph used to call Ze (a local dashboard re-fetch) directly.
    # The companion script then started Tencent sync too, so two concurrent
    # requests could race and the old local snapshot could win the final paint.
    "onClick:Ze,style:{background:": "onClick:()=>window.dispatchEvent(new Event(`welding-tencent-sync`)),style:{background:",
    # The settings button and the header glyph now share the exact same React
    # function.  The function self-loads the persisted setting when the modal
    # has never been opened in this browser session.
    "try{let e=qe(Ce),t=await fetch(`${Ke}/api/tencent/sync`": "try{let e=qe(Ce);if(!e){let t=await fetch(`${Ke}/api/tencent/config`);if(t.ok){let n=await t.json();e=qe(n.book_id||``)}}let t=await fetch(`${Ke}/api/tencent/sync`",
    "}};(0,v.useEffect)(()=>{s&&He(s)},[s]);let Ze=async e=>{": "}};window.__weldingSettingsImmediateSync=Xe,(0,v.useEffect)(()=>{s&&He(s)},[s]);let Ze=async e=>{",
    "(0,v.useEffect)(()=>{Ze();let e=window.setInterval(()=>{(document.querySelector(`.header-left span`)?.textContent||``)!==`WS ?????`&&Ze(!0)},15e3);return()=>window.clearInterval(e)},[])": "(0,v.useEffect)(()=>{let t=()=>Ze(!0);Ze(),window.addEventListener(`welding-dashboard-refresh`,t);let e=window.setInterval(()=>{(document.querySelector(`.header-left span`)?.textContent||``)!==`WS ?????`&&Ze(!0)},15e3);return()=>{window.clearInterval(e),window.removeEventListener(`welding-dashboard-refresh`,t)}},[])",
    "e.onmessage=e=>{try{let t=JSON.parse(e.data);if(t.type===`data_updated`&&t.data){console.log(`Received real-time update payload:`,t.data);let{kpi:e,pipelines:n,ndt_ng:r,latest_welds:a}=t.data;i(e),o(n),_(r),h(a);let s=l.current;s?He(s):n.length>0&&c(n[0].pipeline_no)}}catch(e){console.error(`Error handling WebSocket message:`,e)}}": "e.onmessage=e=>{try{let t=JSON.parse(e.data);if(t.type===`data_updated`&&t.data){console.log(`Received real-time update revision:`,t.revision);let{kpi:e,pipelines:n,ndt_ng:r,latest_welds:a}=t.data,q=Array.isArray(t.changed_pipelines)?t.changed_pipelines:[`*`],u=q.includes(`*`),d=l.current;i(t=>JSON.stringify(t)===JSON.stringify(e)?t:e),o(t=>JSON.stringify(t)===JSON.stringify(n)?t:n),_(t=>JSON.stringify(t)===JSON.stringify(r)?t:r),h(t=>JSON.stringify(t)===JSON.stringify(a)?t:a),d?(u||q.includes(d))&&He(d):n.length>0&&!l.current&&c(n[0].pipeline_no)}}catch(e){console.error(`Error handling WebSocket message:`,e)}}",
}


def main() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    for before, after in REPLACEMENTS.items():
        count = content.count(before)
        if count != 1:
            raise RuntimeError(
                f"Runtime patch anchor must occur once, found {count}: {before[:80]!r}"
            )
        content = content.replace(before, after)
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"[OK] built {OUTPUT.name}")


if __name__ == "__main__":
    main()
