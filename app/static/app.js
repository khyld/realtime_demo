const elements = {
  activity: document.querySelector("#activityText"),
  audio: document.querySelector("#remoteAudio"),
  connection: document.querySelector("#connectionStatus"),
  clearTranscriptButton: document.querySelector("#clearTranscriptButton"),
  documentInput: document.querySelector("#documentInput"),
  deleteDocumentsButton: document.querySelector("#deleteDocumentsButton"),
  eventLog: document.querySelector("#eventLog"),
  knowledgeDocumentList: document.querySelector("#knowledgeDocumentList"),
  microphoneSelect: document.querySelector("#microphoneSelect"),
  microphoneStatus: document.querySelector("#microphoneStatus"),
  questionInput: document.querySelector("#questionInput"),
  refreshDocumentsButton: document.querySelector("#refreshDocumentsButton"),
  sendQuestionButton: document.querySelector("#sendQuestionButton"),
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
  pendingAssistantText: "",
  selectedMicrophoneId: "",
  selectedDocumentIds: new Set(),
};

document.addEventListener("DOMContentLoaded", async () => {
  window.lucide?.createIcons();
  elements.questionInput.disabled = false;
  bindEvents();
  await Promise.all([loadMicrophoneDevices(), loadKnowledgeDocuments(), loadIndexingStatus()]);
});

function bindEvents() {
  elements.start.addEventListener("click", startSession);
  elements.stop.addEventListener("click", () => stopSession("Session stoppet"));
  elements.clearTranscriptButton.addEventListener("click", clearTranscript);
  elements.microphoneSelect.addEventListener("change", () => {
    state.selectedMicrophoneId = elements.microphoneSelect.value;
    elements.microphoneStatus.textContent = `Valgt mikrofon: ${elements.microphoneSelect.options[elements.microphoneSelect.selectedIndex]?.text || "standard"}`;
    logEvent(`Mikrofon valgt: ${elements.microphoneSelect.options[elements.microphoneSelect.selectedIndex]?.text || "standard"}`);
  });
  elements.sendQuestionButton.addEventListener("click", sendTypedQuestion);
  elements.refreshDocumentsButton.addEventListener("click", loadKnowledgeDocuments);
  elements.deleteDocumentsButton.addEventListener("click", deleteSelectedDocuments);
  elements.questionInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendTypedQuestion();
    }
  });
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

async function loadMicrophoneDevices() {
  if (!navigator.mediaDevices?.enumerateDevices) {
    elements.microphoneSelect.disabled = false;
    elements.microphoneSelect.innerHTML = '<option value="">Standardmikrofon</option>';
    elements.microphoneStatus.textContent = "Browseren vælger standardmikrofonen.";
    return;
  }

  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const microphones = devices.filter((device) => device.kind === "audioinput");
    elements.microphoneSelect.innerHTML = "";

    if (!microphones.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "Standardmikrofon";
      elements.microphoneSelect.append(option);
      elements.microphoneSelect.disabled = false;
      elements.microphoneStatus.textContent = "Vælg standardmikrofonen, eller giv browseren mikrofontilladelse.";
      return;
    }

    microphones.forEach((device, index) => {
      const option = document.createElement("option");
      option.value = device.deviceId;
      option.textContent = device.label || `Mikrofon ${index + 1}`;
      elements.microphoneSelect.append(option);
    });

    if (state.selectedMicrophoneId) {
      elements.microphoneSelect.value = state.selectedMicrophoneId;
    } else {
      state.selectedMicrophoneId = microphones[0].deviceId;
      elements.microphoneSelect.value = state.selectedMicrophoneId;
    }

    elements.microphoneSelect.disabled = false;
    elements.microphoneStatus.textContent = "Mikrofonen er klar til brug.";
  } catch (error) {
    logEvent(`Mikrofonliste kunne ikke hentes: ${error.message}`);
    elements.microphoneSelect.disabled = false;
    elements.microphoneSelect.innerHTML = '<option value="">Standardmikrofon</option>';
    elements.microphoneStatus.textContent = "Mikrofonlisten kunne ikke hentes; standardmikrofonen bruges ved start.";
  }
}

function getAudioConstraints() {
  if (!state.selectedMicrophoneId) {
    return { audio: true };
  }

  return {
    audio: {
      deviceId: { exact: state.selectedMicrophoneId },
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  };
}

async function startSession() {
  if (state.peerConnection) return;
  setConnection("connecting", "Forbinder");
  elements.activity.textContent = "Beder om mikrofonadgang";
  elements.start.disabled = true;

  try {
    elements.microphoneStatus.textContent = "Anmoder om mikrofonadgang...";

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

    state.mediaStream = await navigator.mediaDevices.getUserMedia(getAudioConstraints());
    state.mediaStream.getTracks().forEach((track) => state.peerConnection.addTrack(track, state.mediaStream));
    elements.microphoneStatus.textContent = "Mikrofonen er forbundet og klar til samtalen.";

    state.dataChannel = state.peerConnection.createDataChannel("realtime-channel");
    state.dataChannel.addEventListener("open", () => {
      setConnection("connected", "Forbundet");
      elements.activity.textContent = "Lytter";
      elements.stop.disabled = false;
      elements.sendQuestionButton.disabled = false;
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
    elements.microphoneStatus.textContent = "Mikrofonadgang blev nægtet eller kunne ikke startes. Kontrollér browser-tilladelser og prøv igen.";
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
  } else if (event.type === "response.output_text.delta") {
    state.pendingAssistantText += event.delta || "";
    elements.activity.textContent = "Assistenten svarer";
  } else if (event.type === "response.output_text.done") {
    if (state.pendingAssistantText) {
      appendTurn("assistant", state.pendingAssistantText);
      state.pendingAssistantText = "";
    }
  } else if (event.type === "response.output_audio_transcript.done") {
    appendTurn("assistant", event.transcript);
  } else if (event.type === "response.done") {
    if (event.response?.status === "failed") {
      logEvent(event.response.status_details?.error?.message || "Realtime-svaret fejlede");
    }
    elements.activity.textContent = "Lytter";
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

function sendTypedQuestion() {
  const question = elements.questionInput.value.trim();
  if (!question) return;
  if (!state.dataChannel || state.dataChannel.readyState !== "open") {
    elements.microphoneStatus.textContent = "Start samtalen først, før du sender et tekstspørgsmål.";
    return;
  }

  appendTurn("user", question);
  elements.activity.textContent = "Tænker";
  sendRealtimeEvent({
    type: "conversation.item.create",
    item: {
      type: "message",
      role: "user",
      content: [{ type: "input_text", text: question }],
    },
  });
  sendRealtimeEvent({ type: "response.create" });
  elements.questionInput.value = "";
  elements.questionInput.focus();
  logEvent("Tekstspørgsmål sendt til realtime-sessionen");
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
    await loadKnowledgeDocuments();
    await loadIndexingStatus();
  } catch (error) {
    elements.uploadStatus.textContent = error.message;
    elements.uploadButton.disabled = false;
  }
}

async function loadKnowledgeDocuments() {
  try {
    const response = await fetch("/api/knowledge/documents");
    if (!response.ok) throw new Error(await responseMessage(response));
    const result = await response.json();
    renderKnowledgeDocuments(result.documents || []);
  } catch (error) {
    elements.knowledgeDocumentList.replaceChildren();
    const message = document.createElement("p");
    message.className = "document-empty-state";
    message.textContent = `Kunne ikke hente dokumenter: ${error.message}`;
    elements.knowledgeDocumentList.append(message);
    elements.deleteDocumentsButton.disabled = true;
  }
}

function renderKnowledgeDocuments(documents) {
  elements.knowledgeDocumentList.replaceChildren();
  if (!documents.length) {
    const empty = document.createElement("p");
    empty.className = "document-empty-state";
    empty.textContent = "Ingen dokumenter i knowledge base endnu.";
    elements.knowledgeDocumentList.append(empty);
    elements.deleteDocumentsButton.disabled = true;
    return;
  }

  documents.forEach((documentItem) => {
    const item = document.createElement("label");
    item.className = "knowledge-document-item";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = documentItem.document_id;
    checkbox.checked = state.selectedDocumentIds.has(documentItem.document_id);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        state.selectedDocumentIds.add(documentItem.document_id);
      } else {
        state.selectedDocumentIds.delete(documentItem.document_id);
      }
      updateDocumentSelectionState();
    });

    const label = document.createElement("span");
    label.textContent = documentItem.filename;

    item.append(checkbox, label);
    elements.knowledgeDocumentList.append(item);
  });

  updateDocumentSelectionState();
}

function updateDocumentSelectionState() {
  elements.deleteDocumentsButton.disabled = state.selectedDocumentIds.size === 0;
}

async function deleteSelectedDocuments() {
  const documentIds = Array.from(state.selectedDocumentIds);
  if (!documentIds.length) return;

  try {
    const response = await fetch("/api/knowledge/documents", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_ids: documentIds }),
    });
    if (!response.ok) throw new Error(await responseMessage(response));
    const result = await response.json();
    state.selectedDocumentIds.clear();
    elements.uploadStatus.textContent = `${result.deleted_count} dokument${result.deleted_count === 1 ? "" : "er"} slettet.`;
    await loadKnowledgeDocuments();
    await loadIndexingStatus();
  } catch (error) {
    elements.uploadStatus.textContent = error.message;
  }
}

function selectedFilesMessage(files) {
  if (!files.length) return "";
  if (files.length > 10) return "Vælg højst 10 filer ad gangen.";
  if (files.length === 1) return files[0].name;
  return `${files.length} filer valgt`;
}

function clearTranscript() {
  elements.transcript.replaceChildren();
  const emptyState = document.createElement("div");
  emptyState.className = "empty-state";
  emptyState.innerHTML = '<i data-lucide="audio-lines" aria-hidden="true"></i><p>Start mikrofonen og tal naturligt på dansk eller engelsk.</p>';
  elements.transcript.append(emptyState);
  window.lucide?.createIcons();
  logEvent("Samtaleindhold ryddet");
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
  elements.sendQuestionButton.disabled = true;
  if (!state.peerConnection && !state.mediaStream) {
    elements.microphoneStatus.textContent = "Venter på adgang til mikrofonen.";
  }
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

async function loadIndexingStatus() {
  try {
    const response = await fetch("/api/knowledge/indexing-status");
    if (!response.ok) throw new Error(await responseMessage(response));
    const result = await response.json();
    renderIndexingStatus(result);
  } catch (error) {
    elements.uploadStatus.textContent = `Indekseringsstatus kunne ikke hentes: ${error.message}`;
  }
}

function renderIndexingStatus(result) {
  const status = result.last_result_status || result.status;
  if (status === "inProgress" || status === "running") {
    elements.uploadStatus.textContent = "Indekserer dokumenter...";
    window.setTimeout(loadIndexingStatus, 5000);
  } else if (status === "success") {
    elements.uploadStatus.textContent = "Indeksering er færdig.";
  } else if (status === "transientFailure" || status === "persistentFailure" || status === "error") {
    elements.uploadStatus.textContent = `Indeksering fejlede: ${result.error_message || "ukendt fejl"}`;
  }
}