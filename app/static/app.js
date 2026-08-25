const elements = {
  activity: document.querySelector("#activityText"),
  audio: document.querySelector("#remoteAudio"),
  connection: document.querySelector("#connectionStatus"),
  documentInput: document.querySelector("#documentInput"),
  eventLog: document.querySelector("#eventLog"),
  sourceCount: document.querySelector("#sourceCount"),
  sourceList: document.querySelector("#sourceList"),
  start: document.querySelector("#startButton"),
  statusDot: document.querySelector("#statusDot"),
  stop: document.querySelector("#stopButton"),
  transcript: document.querySelector("#transcript"),
  uploadButton: document.querySelector("#uploadButton"),
  uploadForm: document.querySelector("#uploadForm"),
  uploadStatus: document.querySelector("#uploadStatus"),
};

const state = {
  dataChannel: null,
  language: "auto",
  mediaStream: null,
  peerConnection: null,
};

document.addEventListener("DOMContentLoaded", () => {
  window.lucide?.createIcons();
  bindEvents();
});

function bindEvents() {
  elements.start.addEventListener("click", startSession);
  elements.stop.addEventListener("click", () => stopSession("Session stoppet"));
  elements.documentInput.addEventListener("change", () => {
    const files = Array.from(elements.documentInput.files);
    elements.uploadButton.disabled = files.length === 0 || files.length > 10;
    elements.uploadStatus.textContent = selectedFilesMessage(files);
  });
  elements.uploadForm.addEventListener("submit", uploadDocument);
  document.querySelectorAll(".language-option").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".language-option").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      state.language = button.dataset.language;
    });
  });
  window.addEventListener("beforeunload", cleanupSession);
}

async function startSession() {
  if (state.peerConnection) return;
  setConnection("connecting", "Forbinder");
  elements.activity.textContent = "Beder om mikrofonadgang";
  elements.start.disabled = true;

  try {
    const sessionResponse = await fetch("/api/realtime/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language: state.language }),
    });
    if (!sessionResponse.ok) throw new Error(await responseMessage(sessionResponse));
    const session = await sessionResponse.json();

    state.peerConnection = new RTCPeerConnection();
    state.peerConnection.addEventListener("connectionstatechange", handleConnectionState);
    state.peerConnection.addEventListener("track", (event) => {
      elements.audio.srcObject = event.streams[0];
    });

    state.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    state.mediaStream.getTracks().forEach((track) => state.peerConnection.addTrack(track, state.mediaStream));

    state.dataChannel = state.peerConnection.createDataChannel("realtime-channel");
    state.dataChannel.addEventListener("open", () => {
      setConnection("connected", "Forbundet");
      elements.activity.textContent = "Lytter";
      elements.stop.disabled = false;
      logEvent("Data channel åbnet");
    });
    state.dataChannel.addEventListener("message", handleRealtimeEvent);
    state.dataChannel.addEventListener("close", () => logEvent("Data channel lukket"));

    const offer = await state.peerConnection.createOffer();
    await state.peerConnection.setLocalDescription(offer);
    const sdpResponse = await fetch(session.calls_url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${session.token}`,
        "Content-Type": "application/sdp",
      },
      body: offer.sdp,
    });
    if (!sdpResponse.ok) throw new Error(`SDP-forhandling fejlede (${sdpResponse.status})`);
    await state.peerConnection.setRemoteDescription({
      type: "answer",
      sdp: await sdpResponse.text(),
    });
  } catch (error) {
    logEvent(error.message);
    stopSession(error.message, true);
  }
}

function handleConnectionState() {
  const connectionState = state.peerConnection?.connectionState;
  logEvent(`WebRTC: ${connectionState}`);
  if (["failed", "disconnected", "closed"].includes(connectionState)) {
    stopSession("Forbindelsen blev afbrudt", connectionState === "failed");
  }
}

async function handleRealtimeEvent(message) {
  let event;
  try {
    event = JSON.parse(message.data);
  } catch {
    logEvent("Modtog ukendt eventformat");
    return;
  }

  logEvent(event.type);
  if (event.type === "input_audio_buffer.speech_started") {
    elements.activity.textContent = "Du taler";
  } else if (event.type === "input_audio_buffer.speech_stopped") {
    elements.activity.textContent = "Tænker";
  } else if (event.type === "output_audio_buffer.started") {
    elements.activity.textContent = "Assistenten taler";
  } else if (event.type === "output_audio_buffer.stopped") {
    elements.activity.textContent = "Lytter";
  } else if (event.type === "conversation.item.input_audio_transcription.completed") {
    appendTurn("user", event.transcript);
  } else if (event.type === "response.output_audio_transcript.done") {
    appendTurn("assistant", event.transcript);
  } else if (event.type === "response.function_call_arguments.done") {
    await executeKnowledgeTool(event);
  } else if (event.type === "error") {
    logEvent(event.error?.message || "Realtime-fejl");
  }
}

async function executeKnowledgeTool(event) {
  if (event.name !== "search_knowledge_base") return;
  elements.activity.textContent = "Søger i knowledge base";
  try {
    const args = JSON.parse(event.arguments || "{}");
    const response = await fetch("/api/knowledge/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: args.query, language: args.language || state.language }),
    });
    if (!response.ok) throw new Error(await responseMessage(response));
    const result = await response.json();
    renderSources(result.sources || []);
    sendRealtimeEvent({
      type: "conversation.item.create",
      item: {
        type: "function_call_output",
        call_id: event.call_id,
        output: JSON.stringify(result),
      },
    });
    sendRealtimeEvent({ type: "response.create" });
  } catch (error) {
    logEvent(`Knowledge tool: ${error.message}`);
    sendRealtimeEvent({
      type: "conversation.item.create",
      item: {
        type: "function_call_output",
        call_id: event.call_id,
        output: JSON.stringify({ found: false, error: "Knowledge search is unavailable." }),
      },
    });
    sendRealtimeEvent({ type: "response.create" });
  }
}

function sendRealtimeEvent(event) {
  if (state.dataChannel?.readyState === "open") {
    state.dataChannel.send(JSON.stringify(event));
  }
}

async function uploadDocument(event) {
  event.preventDefault();
  const files = Array.from(elements.documentInput.files);
  if (!files.length || files.length > 10) return;
  elements.uploadButton.disabled = true;
  elements.uploadStatus.textContent = `Uploader ${files.length} ${files.length === 1 ? "fil" : "filer"}...`;
  const formData = new FormData();
  files.forEach((file) => formData.append("file", file));
  try {
    const response = await fetch("/api/knowledge/documents", { method: "POST", body: formData });
    if (!response.ok) throw new Error(await responseMessage(response));
    const result = await response.json();
    elements.uploadStatus.textContent = `${result.count} ${result.count === 1 ? "dokument" : "dokumenter"} modtaget. Indeksering er startet.`;
    elements.uploadForm.reset();
  } catch (error) {
    elements.uploadStatus.textContent = error.message;
    elements.uploadButton.disabled = false;
  }
}

function selectedFilesMessage(files) {
  if (!files.length) return "";
  if (files.length > 10) return "Vælg højst 10 filer ad gangen.";
  if (files.length === 1) return files[0].name;
  return `${files.length} filer valgt`;
}

function appendTurn(role, text) {
  if (!text) return;
  elements.transcript.querySelector(".empty-state")?.remove();
  const turn = document.createElement("article");
  turn.className = `turn ${role}`;
  const label = document.createElement("p");
  label.className = "turn-label";
  label.textContent = role === "user" ? "Dig" : "Assistent";
  const content = document.createElement("p");
  content.className = "turn-text";
  content.textContent = text;
  turn.append(label, content);
  elements.transcript.append(turn);
  elements.transcript.scrollTop = elements.transcript.scrollHeight;
}

function renderSources(sources) {
  elements.sourceCount.textContent = String(sources.length);
  elements.sourceList.replaceChildren();
  if (!sources.length) {
    const item = document.createElement("li");
    item.className = "muted";
    item.textContent = "Ingen relevante kilder fundet.";
    elements.sourceList.append(item);
    return;
  }
  sources.forEach((source) => {
    const item = document.createElement("li");
    const title = document.createElement("span");
    title.className = "source-title";
    title.textContent = source.title;
    const excerpt = document.createElement("span");
    excerpt.className = "source-excerpt";
    excerpt.textContent = source.excerpt;
    item.append(title, excerpt);
    elements.sourceList.append(item);
  });
}

function stopSession(message = "Ikke forbundet", isError = false) {
  cleanupSession();
  setConnection(isError ? "error" : "", message);
  elements.activity.textContent = "Klar";
  elements.start.disabled = false;
  elements.stop.disabled = true;
}

function cleanupSession() {
  state.dataChannel?.close();
  state.mediaStream?.getTracks().forEach((track) => track.stop());
  state.peerConnection?.close();
  elements.audio.srcObject = null;
  state.dataChannel = null;
  state.mediaStream = null;
  state.peerConnection = null;
}

function setConnection(mode, text) {
  elements.statusDot.className = `status-dot ${mode}`;
  elements.connection.textContent = text;
}

function logEvent(message) {
  const item = document.createElement("li");
  item.textContent = `${new Date().toLocaleTimeString()} ${message}`;
  elements.eventLog.prepend(item);
  while (elements.eventLog.children.length > 80) elements.eventLog.lastChild.remove();
}

async function responseMessage(response) {
  try {
    const body = await response.json();
    return body.detail || body.error || `Request fejlede (${response.status})`;
  } catch {
    return `Request fejlede (${response.status})`;
  }
}