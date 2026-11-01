// Draws the real LangGraph diagram and follows each step through server events.
"use strict";

const panel = document.getElementById("graph-panel");
const panelStatus = document.getElementById("graph-status");
const diagram = document.getElementById("graph-diagram");
const steps = document.getElementById("graph-steps");

function setStatus(text, panelState) {
  panelStatus.textContent = text;
  panel.dataset.state = panelState;
}

function highlight(nodeName) {
  for (const node of diagram.querySelectorAll(".node.active")) {
    node.classList.remove("active");
  }
  if (!nodeName) return;
  const node = diagram.querySelector(`.node[id*="flowchart-${nodeName}-"]`);
  node?.classList.add("active");
}

function addStep(title, detail, className) {
  const item = document.createElement("li");
  item.textContent = title;
  if (className) item.className = className;
  if (detail) {
    const line = document.createElement("span");
    line.className = "step-detail";
    line.textContent = detail;
    item.append(line);
  }
  steps.append(item);
  steps.scrollTop = steps.scrollHeight;
}

function describeChanges(changes) {
  return Object.entries(changes ?? {})
    .map(([name, value]) => `${name}: ${Array.isArray(value) ? value.join(", ") || "none" : value ?? "none"}`)
    .join(" | ");
}

const eventHandlers = {
  run_start(event) {
    if (!event.resumed) steps.replaceChildren();
    addStep(event.resumed ? "Resumed with your answers" : "Run started");
    highlight("__start__");
    setStatus("Running", "running");
  },
  node_start(event) {
    highlight(event.node);
    setStatus(`Running: ${event.node}`, "running");
  },
  node_end(event) {
    addStep(`${event.node} finished in ${event.ms} ms`, describeChanges(event.changes));
  },
  mcp_start(event) {
    addStep(`MCP call started: ${event.server} ${event.tool}`, "", "step-mcp");
  },
  mcp_end(event) {
    addStep(`MCP call finished: ${event.server} in ${event.ms} ms`, event.result, "step-mcp");
  },
  paused(event) {
    highlight(event.node);
    const missing = `still missing: ${event.missing_fields.join(", ")}`;
    addStep(`${event.node} paused: asking for ${event.field}`, event.error ? `${missing} | ${event.error}` : missing);
    setStatus(`Paused: waiting for ${event.field}`, "paused");
  },
  run_end() {
    addStep("Run complete");
    highlight("__end__");
    setStatus("Complete", "complete");
  },
  run_failed() {
    addStep("Run failed");
    highlight(null);
    setStatus("Failed", "failed");
  },
};

async function drawDiagram() {
  const response = await fetch("/graph");
  if (!response.ok) throw new Error(`The server returned HTTP ${response.status}.`);
  const text = await response.text();
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "strict",
    theme: dark ? "dark" : "default",
  });
  const { svg } = await mermaid.render("graph-svg", text);
  diagram.innerHTML = svg;
}

drawDiagram().catch((error) => {
  diagram.textContent = `The diagram is not available: ${error.message}`;
});

const eventSource = new EventSource("/events");
eventSource.onmessage = (message) => {
  const event = JSON.parse(message.data);
  eventHandlers[event.kind]?.(event);
};
