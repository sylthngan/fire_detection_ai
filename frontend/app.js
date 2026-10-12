(() => {
  "use strict";

  const POLL_INTERVAL_MS = 5000;
  const state = {
    cameras: [],
    locations: [],
    alerts: [],
    history: [],
    stats: {},
    activeView: "dashboard",
    historyTab: "alerts",
    alertFilter: "all",
    classFilter: "all",
    cameraFilter: "",
    search: "",
    seenAlertIds: null,
    incomingAlertId: null,
    selectedAlertId: null,
    acknowledgeAlertId: null,
    resolveAlertId: null,
    soundEnabled: false,
    audioContext: null,
    pollRunning: false,
    pollTimer: null,
    failedConnection: false,
  };

  const $ = (selector) => document.querySelector(selector);
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);

  const api = {
    async request(path, options = {}) {
      const response = await fetch(path, {
        ...options,
        headers: { Accept: "application/json", ...(options.headers || {}) },
      });
      if (!response.ok) {
        let message = `${response.status} ${response.statusText}`;
        try {
          const body = await response.json();
          message = typeof body.detail === "string" ? body.detail : message;
        } catch (error) {
          if (!(error instanceof SyntaxError)) throw error;
        }
        throw new Error(message);
      }
      return response.json();
    },
    acknowledge(id, acknowledgedBy) {
      return this.request(`/api/alerts/${id}/acknowledge`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ acknowledged_by: acknowledgedBy }),
      });
    },
    resolve(id, status, note) {
      return this.request(`/api/alerts/${id}/resolve`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, note }),
      });
    },
  };

  function showToast(message, type = "") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`.trim();
    toast.textContent = message;
    $("#toast-region").append(toast);
    window.setTimeout(() => toast.remove(), 4200);
  }

  function formatDate(value, includeSeconds = false) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    return new Intl.DateTimeFormat("vi-VN", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
      ...(includeSeconds ? { second: "2-digit" } : {}),
    }).format(date);
  }

  function relativeTime(value) {
    if (!value) return "—";
    const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
    if (!Number.isFinite(seconds)) return "—";
    if (seconds < 60) return `${seconds} giây trước`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)} phút trước`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} giờ trước`;
    return `${Math.floor(seconds / 86400)} ngày trước`;
  }

  function normalizedStatus(rawStatus) {
    if (rawStatus === "active") return "normal";
    return "offline";
  }

  function cameraState(cameraId) {
    const camera = state.cameras.find((item) => item.id === cameraId);
    const connection = camera?.status || "disconnected";
    if (connection !== "active") return "offline";
    const openAlerts = state.alerts.filter((item) => item.camera_id === cameraId && item.status === "open");
    if (openAlerts.some((item) => item.alert_class === "fire")) return "fire";
    if (openAlerts.some((item) => item.alert_class === "smoke")) return "smoke";
    return "normal";
  }

  function statusLabel(status) {
    return ({ normal: "Bình thường", fire: "Phát hiện lửa", smoke: "Phát hiện khói", offline: "Ngoại tuyến" })[status] || "Không xác định";
  }

  function classLabel(value) {
    return value === "fire" ? "Lửa" : value === "smoke" ? "Khói" : "Không xác định";
  }

  function isOpen(alert) {
    return alert.status === "open";
  }

  function renderConnection(online, message) {
    const orb = $("#sidebar-orb");
    orb.className = `status-orb ${online ? "online" : "offline"}`;
    $("#sidebar-updated").textContent = message;
    const openAlertCount = state.alerts.filter(isOpen).length;
    const offlineCameraCount = state.cameras.filter((camera) => camera.status !== "active").length;
    const systemState = $("#system-state");
    if (!online) {
      systemState.className = "system-state danger";
      $("#system-state-label").textContent = "Không kết nối được dữ liệu";
    } else if (openAlertCount) {
      systemState.className = "system-state danger";
      $("#system-state-label").textContent = `${openAlertCount} cảnh báo cần theo dõi`;
    } else if (!state.cameras.length || offlineCameraCount) {
      systemState.className = "system-state warning";
      $("#system-state-label").textContent = !state.cameras.length
        ? "Chưa đăng ký camera"
        : `${offlineCameraCount} camera ngoại tuyến`;
    } else {
      systemState.className = "system-state";
      $("#system-state-label").textContent = "Đang giám sát bình thường";
    }
  }

  function renderCameras() {
    $("#camera-count").textContent = String(state.cameras.length);
    const activeCount = state.cameras.filter((camera) => camera.status === "active").length;
    $("#metric-cameras").textContent = String(state.cameras.length);
    $("#metric-cameras-foot").textContent = `${activeCount} đang kết nối · ${state.cameras.length - activeCount} ngoại tuyến`;
    const grid = $("#camera-grid");
    if (!state.cameras.length) {
      grid.innerHTML = `<div class="empty-state">Chưa có camera. Hãy đăng ký camera để hiển thị tại đây.</div>`;
      return;
    }

    grid.innerHTML = state.cameras.map((camera) => {
      const status = cameraState(camera.id);
      const activeAlert = state.alerts.find((item) => item.camera_id === camera.id && item.status === "open");
      const visualClass = status === "offline" ? "offline" : status;
      const detection = status === "fire" ? '<span class="camera-detection"></span>' : status === "smoke" ? '<span class="camera-detection smoke-box"></span>' : "";
      const offlineLabel = status === "offline" ? '<span class="camera-offline-label">NO SIGNAL</span>' : "";
      return `<article class="camera-card">
        <div class="camera-visual ${visualClass}">
          ${detection}<span class="camera-lens" aria-hidden="true">⌾</span>${offlineLabel}
          <span class="visual-label">CAM-${String(camera.id).padStart(3, "0")}</span>
          <span class="visual-rec"><span></span>${status === "offline" ? "OFFLINE" : "REC"}</span>
        </div>
        <div class="camera-info"><div class="camera-meta"><div class="camera-name">${escapeHtml(camera.name)}</div><div class="camera-location">${escapeHtml(camera.location || "Chưa có vị trí")}</div></div><span class="status-badge ${status}">${statusLabel(status)}</span></div>
        ${activeAlert ? `<button class="camera-alert-link" data-alert-id="${activeAlert.id}" type="button">Mở cảnh báo đang hoạt động →</button>` : ""}
      </article>`;
    }).join("");
    renderCameraFilter();
  }

  function renderLocationOptions(selectedValue = $("#camera-location").value) {
    const select = $("#camera-location");
    select.innerHTML = `<option value="">Thêm tên vị trí</option>${state.locations
      .map((location) => `<option value="${location.id}">${escapeHtml(location.name)}${location.address ? ` · ${escapeHtml(location.address)}` : ""}</option>`)
      .join("")}<option value="new">＋ Vị trí mới</option>`;
    if ([...select.options].some((option) => option.value === selectedValue)) {
      select.value = selectedValue;
    }
    updateNewLocationFields();
  }

  function updateNewLocationFields() {
    const isNew = $("#camera-location").value === "new";
    const fields = $("#new-location-fields");
    fields.hidden = !isNew;
    $("#location-name").required = isNew;
    $("#location-address").required = isNew;
  }

  function openCameraDialog() {
    renderLocationOptions("");
    $("#camera-form").reset();
    $("#camera-source").value = "camera-index:0";
    updateNewLocationFields();
    $("#camera-dialog").showModal();
    $("#camera-name").focus();
  }

  async function registerCamera(event) {
    event.preventDefault();
    const form = $("#camera-form");
    if (!form.reportValidity()) return;
    const submitButton = $("#save-camera-button");
    submitButton.disabled = true;
    submitButton.textContent = "Đang lưu…";
    const locationChoice = $("#camera-location").value;
    let locationCreated = false;
    try {
      let locationId = Number(locationChoice);
      if (locationChoice === "new") {
        const location = await api.request("/api/locations", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: $("#location-name").value.trim(),
            address: $("#location-address").value.trim(),
          }),
        });
        locationId = location.id;
        locationCreated = true;
      }
      const camera = await api.request("/api/cameras", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          location_id: locationId,
          name: $("#camera-name").value.trim(),
          source_ref: $("#camera-source").value.trim(),
        }),
      });
      closeDialog("camera-dialog");
      form.reset();
      $("#camera-source").value = "camera-index:0";
      showToast(`Đã thêm camera (ID ${camera.id}).`, "success");
      await refreshData();
    } catch (error) {
      console.error("Không thể đăng ký thêm camera:", error);
      let recoveryHint = "";
      if (locationChoice === "new") {
        await refreshData();
        const existingLocation = state.locations.find(
          (location) => location.name.toLocaleLowerCase("vi") === $("#location-name").value.trim().toLocaleLowerCase("vi"),
        );
        if (existingLocation) {
          renderLocationOptions(String(existingLocation.id));
          recoveryHint = ` Đã chọn nhà/vị trí "${existingLocation.name}"; hãy bấm lưu lại camera.`;
        }
      }
      showToast(
        `Không thể thêm camera: ${error.message}${recoveryHint || (locationCreated ? " Vị trí đã được tạo; hãy chọn lại rồi lưu camera." : "")}`,
        "error",
      );
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "Lưu camera";
    }
  }

  function renderCameraFilter() {
    const select = $("#camera-filter");
    const current = select.value;
    select.innerHTML = '<option value="">Tất cả camera</option>' + state.cameras
      .map((camera) => `<option value="${camera.id}">${escapeHtml(camera.name)}</option>`)
      .join("");
    select.value = state.cameras.some((camera) => String(camera.id) === current) ? current : "";
  }

  function renderAlertList() {
    const alerts = state.alerts.slice(0, 8);
    $("#alert-count").textContent = String(state.alerts.filter(isOpen).length);
    $("#metric-fire").textContent = String(state.alerts.filter((alert) => isOpen(alert) && alert.alert_class === "fire").length);
    $("#metric-smoke").textContent = String(state.alerts.filter((alert) => isOpen(alert) && alert.alert_class === "smoke").length);
    const list = $("#alert-list");
    if (!alerts.length) {
      list.innerHTML = `<div class="empty-state">Chưa có cảnh báo. Camera đang theo dõi bình thường.</div>`;
      return;
    }
    list.innerHTML = alerts.map((alert) => `<button class="alert-item" data-alert-id="${alert.id}" type="button">
      <span class="alert-symbol ${alert.alert_class === "smoke" ? "smoke" : ""}" aria-hidden="true">${alert.alert_class === "fire" ? "♨" : "◌"}</span>
      <span class="alert-copy"><span class="alert-title-row"><span class="alert-title">${classLabel(alert.alert_class)} · ${escapeHtml(alert.camera || `Camera ${alert.camera_id}`)}</span><span class="alert-time">${relativeTime(alert.started_at)}</span></span>
      <span class="alert-meta">${escapeHtml(alert.location || "Chưa rõ vị trí")} · ${Math.round((alert.confidence || 0) * 100)}% tin cậy</span>
      <span class="alert-state ${isOpen(alert) ? "open" : "closed"}">${isOpen(alert) ? (alert.acknowledged_at ? "ĐÃ TIẾP NHẬN" : "CẦN XÁC NHẬN") : "ĐÃ XỬ LÝ"}</span></span>
    </button>`).join("");
  }

  function detectionRow(item, detailed = false) {
    const confidence = Math.round((item.confidence || 0) * 100);
    const time = item.captured_at || item.started_at;
    return `<tr>
      <td><span class="event-tag ${item.detection_class}">${classLabel(item.detection_class)}</span></td>
      <td><span class="event-name">${escapeHtml(item.camera || `Camera ${item.camera_id}`)}</span><span class="event-sub">${detailed ? escapeHtml(item.model || "Mô hình nhận diện") : `Frame #${escapeHtml(item.frame_id)}`}</span></td>
      <td>${detailed ? escapeHtml(item.frame_id ?? item.request_id ?? "—") : escapeHtml(item.location || cameraLocation(item.camera_id))}</td>
      <td><span class="confidence-cell"><span>${confidence}%</span><span class="confidence-track"><span style="width:${Math.min(100, confidence)}%"></span></span></span></td>
      <td class="mono-cell">${formatDate(time)}</td>
    </tr>`;
  }

  function cameraLocation(cameraId) {
    return state.cameras.find((camera) => camera.id === cameraId)?.location || "—";
  }

  function renderRecentHistory() {
    const body = $("#recent-body");
    if (!state.history.length) {
      body.innerHTML = `<tr><td colspan="5" class="table-empty">Chưa có dữ liệu phát hiện từ nhận diện.</td></tr>`;
      return;
    }
    body.innerHTML = state.history.slice(0, 5).map((item) => detectionRow(item)).join("");
  }

  function renderHistory() {
    const alertsTab = state.historyTab === "alerts";
    $("#history-alert-count").textContent = String(state.alerts.length);
    $("#history-detection-count").textContent = String(state.history.length);
    $("#history-total").textContent = String(alertsTab ? state.alerts.length : state.history.length);
    $("#history-head").innerHTML = alertsTab
      ? "<tr><th>LOẠI</th><th>CAMERA / VỊ TRÍ</th><th>ĐỘ TIN CẬY</th><th>TRẠNG THÁI</th><th>THỜI GIAN</th></tr>"
      : "<tr><th>LOẠI</th><th>CAMERA / MODEL</th><th>FRAME</th><th>ĐỘ TIN CẬY</th><th>THỜI GIAN</th></tr>";
    const query = state.search.trim().toLocaleLowerCase("vi");
    const source = alertsTab ? state.alerts : state.history;
    const filtered = source.filter((item) => {
      if (state.cameraFilter && String(item.camera_id) !== state.cameraFilter) return false;
      if (state.classFilter !== "all" && item[alertsTab ? "alert_class" : "detection_class"] !== state.classFilter) return false;
      if (query && !`${item.camera || ""} ${item.location || cameraLocation(item.camera_id) || ""}`.toLocaleLowerCase("vi").includes(query)) return false;
      if (alertsTab) {
        if (state.alertFilter === "open" && !isOpen(item)) return false;
        if (state.alertFilter === "unacknowledged" && (!isOpen(item) || item.acknowledged_at)) return false;
        if (state.alertFilter === "closed" && isOpen(item)) return false;
      }
      return true;
    });
    const body = $("#history-body");
    $("#history-showing").textContent = `Hiển thị ${filtered.length} / ${source.length} bản ghi`;
    $("#history-total").textContent = String(source.length);
    $("#class-filter").hidden = alertsTab;
    $("#alert-filter").hidden = !alertsTab;
    if (!filtered.length) {
      body.innerHTML = `<tr><td colspan="5" class="table-empty">Không tìm thấy ${alertsTab ? "cảnh báo" : "lần phát hiện"} phù hợp.</td></tr>`;
      return;
    }
    body.innerHTML = alertsTab
      ? filtered.map((alert) => `<tr class="history-row" data-alert-id="${alert.id}">
          <td><span class="event-tag ${alert.alert_class}">${classLabel(alert.alert_class)}</span></td>
          <td><span class="event-name">${escapeHtml(alert.camera || `Camera ${alert.camera_id}`)}</span><span class="event-sub">${escapeHtml(alert.location || cameraLocation(alert.camera_id))}</span></td>
          <td><span class="confidence-cell">${Math.round((alert.confidence || 0) * 100)}%<span class="confidence-track"><span style="width:${Math.min(100, Math.round((alert.confidence || 0) * 100))}%"></span></span></span></td>
          <td><span class="ack-badge ${alert.acknowledged_at ? "" : "pending"}">${isOpen(alert) ? alert.acknowledged_at ? "Đã tiếp nhận" : "Chưa xác nhận" : escapeHtml(alert.status === "false_alarm" ? "Cảnh báo sai" : "Đã xử lý")}</span></td>
          <td class="mono-cell">${formatDate(alert.started_at)}</td>
        </tr>`).join("")
      : filtered.map((item) => detectionRow(item, true)).join("");
  }

  function renderStats() {
    $("#metric-events").textContent = String(state.stats.detections ?? state.history.length);
  }

  function renderAll() {
    renderCameras();
    renderAlertList();
    renderRecentHistory();
    renderHistory();
    renderStats();
    renderConnection(true, `Cập nhật ${new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date())}`);
  }

  async function refreshData() {
    if (state.pollRunning) return;
    state.pollRunning = true;
    $("#refresh-button").classList.add("spinning");
    try {
      const [cameras, alerts, history, stats, locations] = await Promise.all([
        api.request("/api/cameras"),
        api.request("/api/alerts?limit=100&offset=0"),
        api.request("/api/detections/history?limit=100&offset=0"),
        api.request("/api/stats"),
        api.request("/api/locations"),
      ]);
      const cameraStatuses = await Promise.all(cameras.map(async (camera) => {
        const status = await api.request(`/api/cameras/${camera.id}/status`);
        return { ...camera, ...status };
      }));

      const previousIds = state.seenAlertIds;
      const incoming = previousIds === null
        ? []
        : alerts.filter((alert) => !previousIds.has(alert.id) && isOpen(alert));
      state.seenAlertIds = new Set(alerts.map((alert) => alert.id));
      state.cameras = cameraStatuses;
      state.locations = locations;
      state.alerts = alerts;
      state.history = history;
      state.stats = stats;
      state.failedConnection = false;
      renderAll();
      if (incoming.length) {
        const newest = incoming[0];
        if (newest.acknowledged_at) return;
        openIncomingAlert(newest);
      }
    } catch (error) {
      console.error("Dashboard refresh failed:", error);
      const wasFailed = state.failedConnection;
      state.failedConnection = true;
      renderConnection(false, "Kiểm tra FastAPI đang chạy");
      if (!wasFailed) showToast(`Không tải được dữ liệu: ${error.message}`, "error");
    } finally {
      state.pollRunning = false;
      $("#refresh-button").classList.remove("spinning");
    }
  }

  function openIncomingAlert(alert) {
    state.incomingAlertId = alert.id;
    const isSmoke = alert.alert_class === "smoke";
    $("#incoming-icon").classList.toggle("smoke", isSmoke);
    $("#incoming-icon").textContent = isSmoke ? "◌" : "!";
    $("#incoming-title").textContent = isSmoke ? "Phát hiện khói" : "Phát hiện lửa";
    $("#incoming-description").textContent = `${alert.camera || `Camera ${alert.camera_id}`} · ${alert.location || "Chưa rõ vị trí"} · Độ tin cậy ${Math.round((alert.confidence || 0) * 100)}%`;
    const dialog = $("#incoming-dialog");
    if (!dialog.open) dialog.showModal();
    playAlertSound();
    showToast(`Cảnh báo mới: ${classLabel(alert.alert_class)} tại ${alert.camera || `Camera ${alert.camera_id}`}`, "error");
  }

  function playAlertSound() {
    if (!state.soundEnabled) return;
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) {
      showToast("Trình duyệt này không hỗ trợ phát âm thanh cảnh báo.", "error");
      return;
    }
    try {
      state.audioContext ||= new AudioContextClass();
      const context = state.audioContext;
      context.resume().then(() => {
        [0, 0.19, 0.38].forEach((offset, index) => {
          const oscillator = context.createOscillator();
          const gain = context.createGain();
          oscillator.type = "sine";
          oscillator.frequency.value = index === 1 ? 740 : 880;
          gain.gain.setValueAtTime(0.0001, context.currentTime + offset);
          gain.gain.exponentialRampToValueAtTime(0.13, context.currentTime + offset + 0.025);
          gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + offset + 0.14);
          oscillator.connect(gain);
          gain.connect(context.destination);
          oscillator.start(context.currentTime + offset);
          oscillator.stop(context.currentTime + offset + 0.15);
        });
      }).catch((error) => {
        console.error("Could not play alert sound:", error);
        showToast("Không phát được cảnh báo. Hãy bật cảnh báo lại sau thao tác người dùng.", "error");
      });
    } catch (error) {
      console.error("Could not initialize alert sound:", error);
      showToast("Không khởi tạo được âm thanh cảnh báo.", "error");
    }
  }

  function openAlertDetail(id) {
    const alert = state.alerts.find((item) => item.id === Number(id));
    if (!alert) {
      showToast("Không tìm thấy chi tiết cảnh báo. Dữ liệu sẽ được làm mới.", "error");
      refreshData();
      return;
    }
    state.selectedAlertId = alert.id;
    $("#detail-title").textContent = `${classLabel(alert.alert_class)} · ${alert.camera || `Camera ${alert.camera_id}`}`;
    const snapshotUrl = alert.snapshot_path ? `/api/alerts/${alert.id}/snapshot` : null;
    $("#detail-content").innerHTML = `
      <div class="detail-image-wrap">${snapshotUrl
        ? `<img src="${snapshotUrl}" alt="Ảnh bằng chứng cảnh báo cháy" onerror="this.outerHTML='<div class=&quot;snapshot-placeholder&quot;>Không tải được ảnh snapshot</div>'">`
        : '<div class="snapshot-placeholder">Không có ảnh snapshot cho sự kiện này</div>'}</div>
      <div class="detail-grid">
        <div class="detail-field"><span>Loại phát hiện</span><strong>${classLabel(alert.alert_class)}</strong></div>
        <div class="detail-field"><span>Độ tin cậy nhận diện</span><strong>${Math.round((alert.confidence || 0) * 100)}%</strong></div>
        <div class="detail-field"><span>Camera</span><strong>${escapeHtml(alert.camera || `Camera ${alert.camera_id}`)}</strong></div>
        <div class="detail-field"><span>Vị trí</span><strong>${escapeHtml(alert.location || cameraLocation(alert.camera_id))}</strong></div>
        <div class="detail-field"><span>Thời gian phát hiện</span><strong>${formatDate(alert.started_at, true)}</strong></div>
        <div class="detail-field"><span>Trạng thái</span><strong>${isOpen(alert) ? alert.acknowledged_at ? "Đã tiếp nhận" : "Chưa xác nhận" : alert.status === "false_alarm" ? "Cảnh báo sai" : "Đã xử lý"}</strong></div>
        ${alert.acknowledged_by ? `<div class="detail-field"><span>Người tiếp nhận</span><strong>${escapeHtml(alert.acknowledged_by)}</strong></div>` : ""}
        ${alert.closed_at ? `<div class="detail-field"><span>Thời gian xử lý</span><strong>${formatDate(alert.closed_at, true)}</strong></div>` : ""}
      </div>
      ${alert.rule_description ? `<div class="detail-rule">${escapeHtml(alert.rule_description)}</div>` : ""}
      ${alert.resolution_note ? `<div class="detail-rule"><strong>Ghi chú:</strong> ${escapeHtml(alert.resolution_note)}</div>` : ""}`;
    const actions = $("#detail-actions");
    actions.innerHTML = "";
    if (isOpen(alert) && !alert.acknowledged_at) {
      actions.insertAdjacentHTML("beforeend", '<button class="button button-outline" data-ack-alert="' + alert.id + '" type="button">Xác nhận đã xem</button>');
    }
    if (isOpen(alert)) {
      actions.insertAdjacentHTML("beforeend", '<button class="button button-primary" data-resolve-alert="' + alert.id + '" type="button">Xử lý cảnh báo</button>');
    }
    $("#detail-dialog").showModal();
  }

  function openAcknowledge(id) {
    state.acknowledgeAlertId = Number(id);
    $("#operator-name").value = localStorage.getItem("fireeyes.operator") || "";
    $("#ack-dialog").showModal();
    $("#operator-name").focus();
  }

  function openResolve(id) {
    state.resolveAlertId = Number(id);
    $("#resolve-note").value = "";
    $("#resolve-status").value = "resolved";
    $("#resolve-dialog").showModal();
  }

  async function acknowledgeSelected(name) {
    const id = state.acknowledgeAlertId;
    if (!id) return;
    const operator = name.trim();
    if (!operator) {
      showToast("Vui lòng nhập tên người xác nhận.", "error");
      return;
    }
    try {
      await api.acknowledge(id, operator);
      localStorage.setItem("fireeyes.operator", operator);
      closeDialog("ack-dialog");
      if ($("#detail-dialog").open) closeDialog("detail-dialog");
      if ($("#incoming-dialog").open && state.incomingAlertId === id) closeDialog("incoming-dialog");
      showToast("Đã lưu xác nhận tiếp nhận cảnh báo.", "success");
      await refreshData();
    } catch (error) {
      showToast(`Không thể xác nhận cảnh báo: ${error.message}`, "error");
    }
  }

  async function resolveSelected(status, note) {
    const id = state.resolveAlertId;
    if (!id) return;
    if (!note.trim()) {
      showToast("Vui lòng nhập ghi chú xử lý.", "error");
      return;
    }
    try {
      await api.resolve(id, status, note.trim());
      closeDialog("resolve-dialog");
      if ($("#detail-dialog").open) closeDialog("detail-dialog");
      showToast(status === "false_alarm" ? "Đã đánh dấu cảnh báo sai." : "Đã xử lý cảnh báo.", "success");
      await refreshData();
    } catch (error) {
      showToast(`Không thể xử lý cảnh báo: ${error.message}`, "error");
    }
  }

  function closeDialog(id) {
    const dialog = document.getElementById(id);
    if (dialog?.open) dialog.close();
  }

  function setView(viewName) {
    state.activeView = viewName;
    document.querySelectorAll(".view-section").forEach((section) => {
      section.classList.toggle("active", section.id === `${viewName}-view`);
    });
    document.querySelectorAll(".nav-link").forEach((button) => {
      button.classList.toggle("active", button.dataset.view === viewName);
    });
    $("#page-name").textContent = viewName === "history" ? "Lịch sử sự kiện" : "Tổng quan";
    if (viewName === "history") renderHistory();
  }

  function bindEvents() {
    document.addEventListener("click", (event) => {
      const viewButton = event.target.closest("[data-view]");
      if (viewButton) {
        setView(viewButton.dataset.view);
        return;
      }
      const alertButton = event.target.closest("[data-alert-id]");
      if (alertButton) {
        openAlertDetail(alertButton.dataset.alertId);
        return;
      }
      const ackButton = event.target.closest("[data-ack-alert]");
      if (ackButton) {
        openAcknowledge(ackButton.dataset.ackAlert);
        return;
      }
      const resolveButton = event.target.closest("[data-resolve-alert]");
      if (resolveButton) openResolve(resolveButton.dataset.resolveAlert);
      const closeButton = event.target.closest("[data-close-dialog]");
      if (closeButton) closeDialog(closeButton.dataset.closeDialog);
    });

    $("#refresh-button").addEventListener("click", refreshData);
    $("#add-camera-button").addEventListener("click", openCameraDialog);
    $("#camera-location").addEventListener("change", updateNewLocationFields);
    $("#camera-form").addEventListener("submit", registerCamera);
    $("#history-search").addEventListener("input", (event) => {
      state.search = event.target.value;
      renderHistory();
    });
    $("#camera-filter").addEventListener("change", (event) => {
      state.cameraFilter = event.target.value;
      renderHistory();
    });
    $("#alert-filter").addEventListener("change", (event) => {
      state.alertFilter = event.target.value;
      renderHistory();
    });
    $("#class-filter").addEventListener("change", (event) => {
      state.classFilter = event.target.value;
      renderHistory();
    });
    document.querySelectorAll("[data-history-tab]").forEach((button) => {
      button.addEventListener("click", () => {
        state.historyTab = button.dataset.historyTab;
        document.querySelectorAll("[data-history-tab]").forEach((tab) => tab.classList.toggle("active", tab === button));
        renderHistory();
      });
    });

    $("#ack-form").addEventListener("submit", (event) => {
      event.preventDefault();
      acknowledgeSelected($("#operator-name").value);
    });
    $("#resolve-form").addEventListener("submit", (event) => {
      event.preventDefault();
      resolveSelected($("#resolve-status").value, $("#resolve-note").value);
    });
    $("#incoming-detail").addEventListener("click", () => {
      const id = state.incomingAlertId;
      closeDialog("incoming-dialog");
      if (id) openAlertDetail(id);
    });
    $("#incoming-dismiss").addEventListener("click", () => closeDialog("incoming-dialog"));
    $("#sound-toggle").addEventListener("click", async () => {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) {
        showToast("Trình duyệt này không hỗ trợ phát cảnh báo.", "error");
        return;
      }
      try {
        state.audioContext ||= new AudioContextClass();
        await state.audioContext.resume();
        state.soundEnabled = !state.soundEnabled;
        $("#sound-toggle").setAttribute("aria-pressed", String(state.soundEnabled));
        $("#sound-label").textContent = state.soundEnabled ? "Tắt cảnh báo" : "Bật cảnh báo";
        showToast(state.soundEnabled ? "Đã bật cảnh báo." : "Đã tắt cảnh báo.", "success");
      } catch (error) {
        console.error("Could not enable alert sound:", error);
        showToast("Không bật được thông báo trong trình duyệt.", "error");
      }
    });
    document.querySelectorAll("dialog").forEach((dialog) => {
      dialog.addEventListener("click", (event) => {
        if (event.target === dialog) dialog.close();
      });
    });
  }

  function initialize() {
    $("#today-label").textContent = new Intl.DateTimeFormat("vi-VN", {
      weekday: "long", day: "2-digit", month: "long", year: "numeric",
    }).format(new Date()).toLocaleUpperCase("vi");
    bindEvents();
    refreshData();
    state.pollTimer = window.setInterval(refreshData, POLL_INTERVAL_MS);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) refreshData();
    });
  }

  initialize();
})();
