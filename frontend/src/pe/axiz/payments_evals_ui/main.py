from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from nicegui import app, html, ui

from pe.axiz.payments_evals_ui.client import BackendClient

ASSETS = Path(__file__).resolve().parents[4] / "assets"
app.add_static_files("/assets", str(ASSETS))
client = BackendClient()


@ui.page("/")
async def index() -> None:
    state: dict[str, Any] = {
        "workspace": "chat",
        "messages": [],
        "active_run_id": None,
        "active_trace": None,
        "auto_scroll": True,
    }

    ui.add_head_html("""
    <style>
    :root { --bg:#071018; --panel:#0a1620; --panel2:#0d1d29; --line:#183447; --text:#cde2ec; --muted:#6e899a; --cyan:#43c3ec; --green:#4bd8a0; }
    body { background:var(--bg); color:var(--text); font-family:Inter,ui-sans-serif,system-ui,sans-serif; }
    .q-page { background:var(--bg); }
    .lab-shell { min-height:100vh; display:grid; grid-template-columns:250px minmax(0,1fr); }
    .lab-rail { background:#08131c; border-right:1px solid var(--line); padding:18px 14px; position:sticky; top:0; height:100vh; overflow:auto; }
    .lab-logo { width:92px; margin:2px 0 20px 5px; }
    .section-title { color:#506b7d; font-size:10px; font-weight:700; letter-spacing:.09em; text-transform:uppercase; margin:22px 7px 8px; }
    .nav-btn { width:100%; justify-content:flex-start; border-radius:9px; color:#8fa7b7; margin:2px 0; }
    .nav-btn.active { background:#0d2634; color:#c6e9f5; border:1px solid #1d465c; }
    .main-column { min-width:0; display:grid; grid-template-rows:auto minmax(0,1fr); height:100vh; }
    .topbar { display:flex; justify-content:space-between; align-items:center; padding:16px 24px; border-bottom:1px solid var(--line); background:rgba(7,16,24,.96); }
    .topbar h1 { margin:0; font-size:20px; font-weight:720; }
    .status { color:#7f9bad; font-size:11px; margin-top:5px; }
    .status.online:before { content:''; display:inline-block; width:7px; height:7px; margin-right:7px; border-radius:50%; background:var(--green); }
    .status.offline:before { content:''; display:inline-block; width:7px; height:7px; margin-right:7px; border-radius:50%; background:#d8757e; }
    .chips { display:flex; flex-wrap:wrap; justify-content:flex-end; gap:6px; }
    .chip { border:1px solid #24536a; border-radius:999px; padding:4px 8px; color:#83c4d9; font-size:9px; }
    .workspace { min-height:0; overflow:auto; padding:18px 24px 28px; }
    .chat-thread { width:min(1000px,100%); margin:0 auto; display:grid; gap:13px; padding-bottom:125px; }
    .message-row { display:flex; gap:10px; align-items:flex-start; }
    .message-row.user { justify-content:flex-end; }
    .avatar { width:38px; height:38px; border-radius:10px; border:1px solid #2c91b0; padding:2px; background:#0d2634; }
    .bubble { max-width:82%; border:1px solid #1b3b50; border-radius:13px; background:#091923; padding:12px 14px; color:#c0d6e0; font-size:13px; line-height:1.55; }
    .user .bubble { background:#0d2a36; border-color:#24556b; }
    .activity { border-bottom:1px solid #153044; padding-bottom:8px; margin-bottom:9px; color:#7fc5da; font-size:11px; }
    .activity small { display:block; color:#5b7889; margin-top:3px; }
    .composer-wrap { position:fixed; left:250px; right:0; bottom:0; z-index:20; background:linear-gradient(180deg,rgba(7,16,24,0),#071018 25%); padding:18px 24px 14px; }
    .composer { width:min(1000px,100%); margin:0 auto; border:1px solid #24475c; border-radius:14px; background:#0a1923; padding:8px 9px; display:flex; gap:8px; align-items:flex-end; box-shadow:0 15px 34px rgba(0,0,0,.28); }
    .composer .q-field { flex:1; }
    .composer-hint { text-align:center; color:#4f697a; font-size:9px; margin-top:5px; }
    .hero { min-height:48vh; display:grid; place-content:center; text-align:center; color:#6f899a; }
    .hero img { width:78px; margin:0 auto 13px; border-radius:18px; }
    .hero h2 { color:#cce9f3; font-size:24px; margin:0 0 5px; }
    .hero p { max-width:680px; font-size:12px; line-height:1.6; }
    .kpi-grid { display:grid; grid-template-columns:repeat(4,minmax(150px,1fr)); gap:10px; margin-bottom:14px; }
    .kpi { border:1px solid #1b3a4d; border-radius:12px; background:#0a1822; padding:13px; }
    .kpi strong { display:block; color:#9de7fb; font-size:20px; }
    .kpi span { color:#6c8798; font-size:10px; }
    .panel { border:1px solid #1a3548; border-radius:14px; background:#091720; padding:14px; margin-bottom:12px; }
    .panel h2,.panel h3 { margin:0 0 10px; color:#c7e7f1; }
    .metric-table { width:100%; border-collapse:collapse; font-size:11px; }
    .metric-table th,.metric-table td { border-bottom:1px solid #142a38; padding:8px; text-align:left; }
    .metric-table th { color:#6f899a; font-size:9px; text-transform:uppercase; letter-spacing:.05em; }
    .pass { color:#62d9a3; } .fail { color:#e59ba4; }
    .trace-json { white-space:pre-wrap; word-break:break-word; color:#90a9b8; font-size:10px; background:#07131b; border-radius:8px; padding:10px; }
    @media(max-width:900px){ .lab-shell{grid-template-columns:1fr}.lab-rail{display:none}.composer-wrap{left:0}.chips{display:none}.kpi-grid{grid-template-columns:repeat(2,1fr)} }
    </style>
    """)

    with ui.element("div").classes("lab-shell"):
        with ui.element("aside").classes("lab-rail"):
            ui.image("/assets/axiz-logo@2x.png").classes("lab-logo")
            ui.button("Nueva conversación", on_click=lambda: new_chat()).props("flat no-caps").classes("nav-btn")
            ui.label("Workspace").classes("section-title")
            nav_buttons: dict[str, Any] = {}
            for key, label in (
                ("chat", "Chat / RAG Playground"),
                ("overview", "Overview de Evals"),
                ("rag", "RAG y Retrieval"),
                ("agent", "Agentic y Conversación"),
                ("routing", "Routing y Graph"),
                ("safety", "Prompts, Safety y Red Team"),
                ("voice", "Voice Evals"),
                ("regression", "Performance y Regresión"),
            ):
                button = ui.button(label, on_click=lambda k=key: switch_workspace(k)).props("flat no-caps").classes("nav-btn")
                nav_buttons[key] = button
            ui.label("Dataset").classes("section-title")
            ui.label("Corpus controlado de payment processing").classes("text-[10px] text-[#6f899a] px-2")
            ui.label("Golden cases · routing · graph · safety · voz").classes("text-[9px] text-[#50697a] px-2 mt-1")
            ui.label("Estrategias").classes("section-title")
            ui.label("Native · Hybrid · GraphRAG · RAGLight · LightRAG").classes("text-[9px] text-[#6f899a] px-2")

        with ui.element("main").classes("main-column"):
            with ui.element("header").classes("topbar"):
                with ui.column().classes("gap-0"):
                    title = ui.label("Payments Agentic RAG Evals Lab").classes("text-xl font-semibold")
                    status = ui.label("Verificando backend").classes("status offline")
                with ui.element("div").classes("chips"):
                    for item in ("SSE streaming", "Golden Dataset", "DeepEval", "RAGAS", "Promptfoo", "Quality gates"):
                        ui.label(item).classes("chip")
            workspace = ui.element("section").classes("workspace")

    def set_active_nav() -> None:
        for key, button in nav_buttons.items():
            button.classes(remove="active")
            if key == state["workspace"]:
                button.classes(add="active")

    async def check_health() -> None:
        try:
            await client.health()
            status.text = "Servicios disponibles"
            status.classes(remove="offline", add="online")
        except Exception:
            status.text = "Backend no disponible"
            status.classes(remove="online", add="offline")

    def new_chat() -> None:
        state["messages"] = []
        state["active_trace"] = None
        state["workspace"] = "chat"
        render_workspace()

    def switch_workspace(key: str) -> None:
        state["workspace"] = key
        set_active_nav()
        render_workspace()

    async def send_message(question_input: Any, strategy_input: Any, send_button: Any) -> None:
        question = (question_input.value or "").strip()
        if not question:
            return
        question_input.value = ""
        send_button.disable()
        state["messages"].append({"role": "user", "content": question})
        assistant = {"role": "assistant", "content": "", "steps": [], "streaming": True, "response": None}
        state["messages"].append(assistant)
        render_workspace()
        payload = {"question": question, "strategy": strategy_input.value, "top_k": 5, "include_case_draft": True}
        try:
            async for event in client.stream_chat(payload):
                event_type = event.get("event")
                if event_type in {"received", "routing", "tool", "retrieval", "generation", "completed"}:
                    assistant["steps"].append({"label": event.get("label", event_type), "detail": event.get("detail", "")})
                elif event_type == "result":
                    assistant["response"] = event.get("response")
                    assistant["content"] = assistant["response"].get("answer", "")
                    state["active_trace"] = assistant["response"].get("trace_id")
                elif event_type == "error":
                    assistant["content"] = f"Error de ejecución: {event.get('error', 'sin detalle')}"
                render_workspace()
                await asyncio.sleep(0)
        finally:
            assistant["streaming"] = False
            send_button.enable()
            render_workspace()

    def render_chat() -> None:
        workspace.clear()
        with workspace:
            if not state["messages"]:
                with ui.element("div").classes("hero"):
                    ui.image("/assets/axiz-agent-icon.png")
                    ui.label("Evals Playground").classes("text-2xl font-semibold text-[#cce9f3]")
                    ui.label("Analiza pagos, compara estrategias RAG, observa tools y trazas, y ejecuta suites reproducibles de calidad, seguridad y regresión.")
            with ui.element("div").classes("chat-thread"):
                for message in state["messages"]:
                    row_class = "message-row user" if message["role"] == "user" else "message-row"
                    with ui.element("div").classes(row_class):
                        if message["role"] == "assistant":
                            ui.image("/assets/axiz-agent-icon.png").classes("avatar")
                        with ui.element("div").classes("bubble"):
                            if message.get("steps"):
                                with ui.element("div").classes("activity"):
                                    ui.label("Actividad de ejecución")
                                    for step in message["steps"][-5:]:
                                        ui.label(f"{step['label']} — {step['detail']}").classes("text-[10px] text-[#5f7d8f]")
                            ui.label(message.get("content") or ("Procesando..." if message.get("streaming") else ""))
                            response = message.get("response")
                            if response:
                                timing = response.get("timings_ms", {})
                                ui.label(f"{response.get('selected_strategy')} · retrieval {timing.get('retrieval', 0):.0f} ms · total {timing.get('total', 0):.0f} ms").classes("text-[9px] text-[#608092] mt-2")
                                with ui.expansion("Evidencia y tools").classes("w-full text-xs"):
                                    for context in response.get("contexts", [])[:5]:
                                        ui.label(f"{context['source']} · score {context['score']:.3f}").classes("text-[#86ccdf]")
                                        ui.label(context["text"][:420]).classes("text-[10px] text-[#7894a4]")
                                    for call in response.get("tools", []):
                                        ui.label(f"tool: {call['tool']} · {call['latency_ms']:.1f} ms").classes("text-[10px] text-[#66d0a3]")
            with ui.element("div").classes("composer-wrap"):
                with ui.element("div").classes("composer"):
                    question_input = ui.textarea(placeholder="Pregunta sobre payment processing...").props("autogrow borderless").classes("w-full")
                    strategy_input = ui.select(["auto", "native", "hybrid", "graphrag", "raglight", "lightrag"], value="auto", label="Estrategia").props("dense outlined").classes("w-40")
                    send_button = ui.button("Enviar").props("unelevated no-caps")
                    send_button.on_click(lambda: send_message(question_input, strategy_input, send_button))
                ui.label("El streaming SSE conserva la traza observable; no se registra razonamiento privado.").classes("composer-hint")

    async def start_run(suite: str, strategy: str) -> None:
        try:
            created = await client.create_run(suite, strategy)
            state["active_run_id"] = created["run_id"]
            ui.notify(f"Suite {suite} iniciada", type="positive")
            for _ in range(180):
                run = await client.get_run(created["run_id"])
                if run["status"] in {"completed", "failed", "cancelled"}:
                    break
                await asyncio.sleep(0.5)
            render_workspace()
        except Exception as exc:
            ui.notify(f"No se pudo ejecutar la suite: {exc}", type="negative")

    def grouped_metrics(run: dict) -> dict[str, list[dict]]:
        groups: dict[str, list[dict]] = defaultdict(list)
        for item in run.get("metrics", []):
            groups[item.get("dimension", "other")].append(item)
        return groups

    def render_dashboard(filter_dimensions: set[str] | None = None) -> None:
        workspace.clear()
        with workspace:
            with ui.element("div").classes("panel"):
                ui.label("Ejecutar suite").classes("text-lg font-semibold")
                with ui.row().classes("items-end gap-2"):
                    suite_select = ui.select(["smoke", "rag", "agentic", "safety", "voice", "full"], value="full", label="Suite").classes("w-44")
                    strategy_select = ui.select(["auto", "native", "hybrid", "graphrag", "raglight", "lightrag"], value="auto", label="Estrategia").classes("w-44")
                    ui.button("Ejecutar", on_click=lambda: start_run(suite_select.value, strategy_select.value)).props("unelevated no-caps")
            run_id = state.get("active_run_id")
            if not run_id:
                ui.label("Todavía no existe un run seleccionado. Se puede iniciar una suite desde este panel.").classes("text-[#6f899a]")
                return
            async def load_and_render() -> None:
                try:
                    run = await client.get_run(run_id)
                except Exception as exc:
                    ui.notify(str(exc), type="negative")
                    return
                groups = grouped_metrics(run)
                metrics = [item for dimension, items in groups.items() if not filter_dimensions or dimension in filter_dimensions for item in items]
                score_values = [item["score"] for item in metrics if item.get("score") is not None]
                with ui.element("div").classes("kpi-grid"):
                    for label, value in (
                        ("Estado", run["status"]),
                        ("Quality score", f"{mean(score_values):.3f}" if score_values else "—"),
                        ("Quality gates", "PASS" if run.get("gates_passed") else "FAIL"),
                        ("Métricas", str(len(metrics))),
                    ):
                        with ui.element("div").classes("kpi"):
                            ui.label(value).classes("text-xl font-semibold text-[#9de7fb]")
                            ui.label(label).classes("text-[10px] text-[#6c8798]")
                if run.get("gate_failures"):
                    with ui.element("div").classes("panel"):
                        ui.label("Gates fallidos").classes("text-base font-semibold")
                        for failure in run["gate_failures"][:25]:
                            ui.label(failure).classes("text-[11px] text-[#e59ba4]")
                with ui.element("div").classes("panel"):
                    ui.label("Resultados normalizados").classes("text-base font-semibold")
                    with ui.element("table").classes("metric-table"):
                        with ui.element("thead"):
                            with ui.element("tr"):
                                for heading in ("Dimensión", "Métrica", "Framework", "Score", "Threshold", "Estado", "Caso"):
                                    html.th(heading)
                        with ui.element("tbody"):
                            for item in metrics:
                                with ui.element("tr"):
                                    html.td(item.get("dimension", ""))
                                    html.td(item.get("metric", ""))
                                    html.td(item.get("framework", ""))
                                    html.td("—" if item.get("score") is None else f"{item['score']:.3f}")
                                    html.td("—" if item.get("threshold") is None else f"{item['threshold']:.3f}")
                                    cell = html.td("PASS" if item.get("passed") is not False else "FAIL")
                                    cell.classes("pass" if item.get("passed") is not False else "fail")
                                    html.td(item.get("case_id") or "")
            ui.timer(0.01, load_and_render, once=True)

    def render_trace() -> None:
        workspace.clear()
        with workspace:
            ui.label("Trazabilidad").classes("text-xl font-semibold")
            trace_id = state.get("active_trace")
            if not trace_id:
                ui.label("No existe una traza activa. Ejecuta una consulta desde el chat.").classes("text-[#6f899a]")
                return
            async def load() -> None:
                try:
                    trace = await client.trace(trace_id)
                    ui.code(str(trace)).classes("trace-json w-full")
                except Exception as exc:
                    ui.notify(str(exc), type="negative")
            ui.timer(0.01, load, once=True)

    def render_workspace() -> None:
        set_active_nav()
        key = state["workspace"]
        if key == "chat":
            render_chat()
        elif key == "overview":
            render_dashboard()
        elif key == "rag":
            render_dashboard({"retrieval", "rag_retrieval", "rag_generation", "prompt"})
        elif key == "agent":
            render_dashboard({"agentic", "conversation", "robustness"})
        elif key == "routing":
            render_dashboard({"routing", "graph"})
        elif key == "safety":
            render_dashboard({"safety", "adversarial", "prompt"})
        elif key == "voice":
            render_dashboard({"voice_stt", "voice_tts", "voice_performance", "voice_conversation"})
        elif key == "regression":
            render_dashboard({"performance", "regression", "drift"})
        else:
            render_trace()

    await check_health()
    render_workspace()


def main() -> None:
    ui.run(
        host=os.getenv("FRONTEND_HOST", "0.0.0.0"),
        port=int(os.getenv("FRONTEND_PORT", "8080")),
        title="Payments Agentic RAG Evals Lab",
        favicon="/assets/axiz-agent-icon.png",
        reload=False,
        show=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
