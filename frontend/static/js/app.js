// VERSION: 5.0 - Fixed avg runtime calculation
console.log("🔧 App.js loaded - VERSION 5.0");
const API_BASE = "/api";
const DEFAULT_TIME_ZONE = "America/Denver";

// Track recent overrides to prevent immediate refresh conflicts
let recentOverrides = new Map(); // zoneName -> timestamp

const zonesTable = document.querySelector("#zonesTable tbody");
const eventsTableBody = document.querySelector("#eventsTable tbody");
const statsTableBody = document.querySelector("#zoneStatsTable tbody");
const refreshZonesBtn = document.getElementById("refreshZones");
const refreshEventsBtn = document.getElementById("refreshEvents");
const statsRefreshBtn = document.querySelector("#refreshStats");
const statsWindowSelect = document.getElementById("statsWindow");
const statsDayInput = document.getElementById("statsDay");
const statsSummaryLabel = document.getElementById("statsSummaryLabel");
const statsCallsHeader = document.getElementById("statsCallsHeader");
const statsTotalHeader = document.getElementById("statsTotalHeader");
const outsideTempEl = document.querySelector("#outsideTemp");
const systemUpdatedEl = document.querySelector("#systemUpdated");
const piStatusEl = document.getElementById("piStatus");
const zoneSelect = document.querySelector("#zoneSelect");
const daySelect = document.querySelector("#daySelect");
const chartCanvas = document.getElementById("zoneChart");
const chartEmpty = document.getElementById("chartEmpty");
const chartCtx = chartCanvas ? chartCanvas.getContext("2d") : null;
const graphsGrid = document.getElementById("graphsGrid");
const graphsDayInput = document.getElementById("graphsDay");
const graphsDayWrapper = document.getElementById("graphsDayWrapper");
const graphsMonthWrapper = document.getElementById("graphsMonthWrapper");
const graphsMonthSelect = document.getElementById("graphsMonth");
const graphsRangeSelect = document.getElementById("graphsRange");
const graphsRefreshBtn = document.getElementById("refreshGraphs");
const graphsClearBtn = document.getElementById("graphsClearDay");
const graphsInfo = document.getElementById("graphsInfo");
const scheduleModal = document.getElementById("scheduleModal");
const scheduleZoneLabel = document.getElementById("scheduleZoneLabel");
const scheduleInfo = document.getElementById("scheduleInfo");
const scheduleErrorEl = document.getElementById("scheduleError");
const scheduleTableBody = document.querySelector("#scheduleTable tbody");
const scheduleEmptyEl = document.getElementById("scheduleEmpty");
const addScheduleRowBtn = document.getElementById("addScheduleRow");
const saveScheduleBtn = document.getElementById("saveSchedule");
const cancelScheduleBtn = document.getElementById("cancelSchedule");
const closeScheduleBtn = document.getElementById("closeSchedule");
const copyDaySourceSelect = document.getElementById("copyDaySource");
const copyDayTargetSelect = document.getElementById("copyDayTargets");
const copyDayBtn = document.getElementById("copyDayBtn");
const copyZonesSelect = document.getElementById("copyZonesSelect");
const copyZonesBtn = document.getElementById("copyZonesBtn");
const presetSelect = document.getElementById("presetSelect");
const applyPresetBtn = document.getElementById("applyPresetBtn");
const deletePresetBtn = document.getElementById("deletePresetBtn");
const savePresetBtn = document.getElementById("savePresetBtn");
const loadGlobalBtn = document.getElementById("loadGlobalBtn");
const clearScheduleBtn = document.getElementById("clearScheduleBtn");
const manageGlobalBtn = document.getElementById("manageGlobalBtn");
const openGlobalScheduleBtn = document.getElementById("openGlobalSchedule");
const useGlobalForAutoBtn = document.getElementById("useGlobalForAuto");
const openSchedulerViewBtn = document.getElementById("openSchedulerView");
const schedulerGrid = document.getElementById("schedulerGrid");
const schedulerGridWrapper = document.getElementById("schedulerGridWrapper");
const schedulerZoneSelect = document.getElementById("schedulerZoneSelect");
const schedulerTimeRow = document.getElementById("schedulerTimeRow");
const schedulerBody = document.getElementById("schedulerBody");
const schedulerStatusNote = document.querySelector(".scheduler-note");
const schedulerAddBtn = document.getElementById("schedulerAddBtn");
const schedulerSaveBtn = document.getElementById("schedulerSaveBtn");
const schedulerResetBtn = document.getElementById("schedulerResetBtn");
const schedulerCopyDaySource = document.getElementById("schedulerCopyDaySource");
const schedulerCopyDayTargets = document.getElementById("schedulerCopyDayTargets");
const schedulerCopyDayBtn = document.getElementById("schedulerCopyDayBtn");
const schedulerCopyZoneTargets = document.getElementById("schedulerCopyZoneTargets");
const schedulerCopyZoneBtn = document.getElementById("schedulerCopyZoneBtn");
const schedulerPresetSelect = document.getElementById("schedulerPresetSelect");
const schedulerPresetApplyBtn = document.getElementById("schedulerPresetApplyBtn");
const schedulerPresetSaveBtn = document.getElementById("schedulerPresetSaveBtn");
const schedulerPresetApplyGlobalBtn = document.getElementById("schedulerPresetApplyGlobalBtn");
const schedulerPresetPreviewBtn = document.getElementById("schedulerPresetPreviewBtn");
const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTH_LABELS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];
const SCHEDULER_DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const SCHEDULER_SLOTS = 48;
const API_DAY_OFFSET = 6;

function apiDayToGridDay(apiDay) {
  return (Number(apiDay) + 1) % 7;
}

function gridDayToApiDay(gridDay) {
  return (Number(gridDay) + API_DAY_OFFSET) % 7;
}
const ZONE_CHOICES = Array.isArray(window.__ZONE_CHOICES__)
  ? window.__ZONE_CHOICES__.map((z) =>
    typeof z === "string" ? { zone: z, room: z } : z
  )
  : [];
let activeScheduleZone = null;
let scheduleDirty = false;
let originalScheduleSnapshot = "[]";
let isGlobalSchedule = false;
let presetsCache = [];
let presetsLoaded = false;
const schedulerState = {};
let activeBubbleEditor = null;
let activeBubbleDrag = null;
const pageLoadingEl = document.getElementById("pageLoading");

function setPageLoading(active) {
  if (!pageLoadingEl) return;
  if (active) {
    pageLoadingEl.classList.remove("hidden");
  } else {
    pageLoadingEl.classList.add("hidden");
  }
}
const graphsState = {
  cards: [],
  cardMap: new Map(),
  resizeTimer: null,
  lastMeta: null,
};
const graphsCache = new Map();
const GRAPHS_CACHE_TTL = 60000;
const DASHBOARD_ZONES_CACHE_KEY = "dashboard.zones";
const DASHBOARD_EVENTS_CACHE_KEY = "dashboard.events";
const DASHBOARD_STATS_CACHE_KEY = "dashboard.stats";
const DASHBOARD_CACHE_TTL = 60000;
const DASHBOARD_CACHE_DEBUG = true;

function generateId() {
  if (window.crypto && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `id-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function resetScheduleMessage() {
  if (scheduleErrorEl) {
    scheduleErrorEl.textContent = "";
    scheduleErrorEl.classList.remove("success");
  }
}

function showScheduleSuccess(message) {
  if (scheduleErrorEl) {
    scheduleErrorEl.textContent = message;
    scheduleErrorEl.classList.add("success");
  }
}

function showScheduleError(message) {
  if (scheduleErrorEl) {
    scheduleErrorEl.textContent = message;
    scheduleErrorEl.classList.remove("success");
  }
}

// Tiny wrapper around fetch that raises an exception on HTTP errors.
async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }
  return response.json();
}

// Display helper that returns a pretty string or an em dash when missing.
function formatTemp(value) {
  if (value === null || value === undefined) return "—";
  return Number.parseFloat(value).toFixed(1);
}

function formatDuration(value) {
  if (value === null || value === undefined) return "—";
  const total = Math.max(0, Math.round(value));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const parts = [];
  if (hours) parts.push(`${hours}h`);
  if (minutes || hours) parts.push(`${minutes}m`);
  parts.push(`${seconds}s`);
  return parts.join(" ");
}

function createCell(text) {
  const td = document.createElement("td");
  td.textContent = text;
  return td;
}

function getProp(obj, ...keys) {
  if (!obj) return undefined;
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(obj, key) && obj[key] !== undefined && obj[key] !== null) {
      return obj[key];
    }
  }
  return undefined;
}

function parseUtcTimestamp(value) {
  if (!value) return null;
  const normalised = value.includes("Z") ? value : `${value}Z`;
  const parsed = new Date(normalised);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function getTimezoneOffsetMs(date, timeZone) {
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  const parts = formatter.formatToParts(date);
  const values = {};
  for (const part of parts) {
    if (part.type !== "literal") {
      values[part.type] = part.value;
    }
  }
  const utcEquivalent = Date.UTC(
    Number.parseInt(values.year, 10),
    Number.parseInt(values.month, 10) - 1,
    Number.parseInt(values.day, 10),
    Number.parseInt(values.hour, 10),
    Number.parseInt(values.minute, 10),
    Number.parseInt(values.second, 10)
  );
  return utcEquivalent - date.getTime();
}

function getTodayIso(timeZone) {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  return formatter.format(new Date());
}

function getDayWindow(day, timeZone, spanDays = 1) {
  if (!day) return null;
  const [yearStr, monthStr, dayStr] = day.split("-");
  const year = Number.parseInt(yearStr, 10);
  const month = Number.parseInt(monthStr, 10);
  const dayNum = Number.parseInt(dayStr, 10);
  if ([year, month, dayNum].some(Number.isNaN)) {
    return null;
  }
  const normalizedSpan = Math.max(1, Math.min(spanDays, 31));
  const startGuess = Date.UTC(year, month - 1, dayNum, 0, 0, 0);
  const startOffset = getTimezoneOffsetMs(new Date(startGuess), timeZone);
  const startUtcMs = startGuess - startOffset;
  const endGuess = Date.UTC(year, month - 1, dayNum + normalizedSpan, 0, 0, 0);
  const endOffset = getTimezoneOffsetMs(new Date(endGuess), timeZone);
  const endUtcMs = endGuess - endOffset;
  const startLocalMs =
    startUtcMs + getTimezoneOffsetMs(new Date(startUtcMs), timeZone);
  return {
    startUtcMs,
    endUtcMs,
    startLocalMs,
    spanDays: normalizedSpan,
  };
}

function splitTimestamp(value) {
  if (!value) return ["", ""];
  const normalised = value.replace(" ", "T");
  const [datePart = "", timeRaw = ""] = normalised.split("T");
  let cleanTime = timeRaw.replace("Z", "");
  if (cleanTime.includes(".")) {
    cleanTime = cleanTime.split(".")[0];
  }
  return [datePart, cleanTime];
}

function formatTime(value) {
  if (!value) return "";
  const parts = value.split(":");
  if (parts.length < 2) return value;
  return parts.slice(0, 3).join(":");
}

// Convert UTC timestamp to local time for display
function convertUTCToLocal(utcDateStr, utcTimeStr) {
  if (!utcDateStr || !utcTimeStr) return { date: utcDateStr, time: utcTimeStr };

  try {
    // Combine date and time, treat as UTC
    const utcString = `${utcDateStr}T${utcTimeStr}Z`;
    const utcDate = new Date(utcString);

    if (isNaN(utcDate.getTime())) {
      return { date: utcDateStr, time: utcTimeStr };
    }

    // Convert to local time
    const localDate = utcDate.toLocaleDateString('en-CA'); // YYYY-MM-DD format
    const localTime = utcDate.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });

    return { date: localDate, time: localTime };
  } catch (e) {
    console.warn('Error converting UTC to local:', e);
    return { date: utcDateStr, time: utcTimeStr };
  }
}

function normaliseScheduleEntry(entry) {
  return {
    day: entry.day_of_week ?? entry.DayOfWeek ?? 0,
    start: (entry.start_time ?? entry.StartTime ?? "06:00").slice(0, 5),
    end: (entry.end_time ?? entry.EndTime ?? "09:00").slice(0, 5),
    setpoint: Number.parseFloat(entry.setpoint_f ?? entry.Setpoint_F ?? 68),
    enabled: Boolean(entry.enabled ?? entry.Enabled ?? true),
  };
}

function populateDaySelectors(selectedSource, selectedTargets = []) {
  const now = new Date();
  const jsDay = now.getDay();
  const fallbackDay = (jsDay + 6) % 7; // Convert Sunday=0 to Monday=0
  const sourceDay =
    typeof selectedSource === "number" && selectedSource >= 0
      ? selectedSource
      : fallbackDay;

  if (copyDaySourceSelect) {
    copyDaySourceSelect.innerHTML = DAY_LABELS.map(
      (label, idx) => `<option value="${idx}" ${idx === sourceDay ? "selected" : ""}>${label}</option>`
    ).join("");
    copyDaySourceSelect.value = String(sourceDay);
  }

  if (copyDayTargetSelect) {
    const targetSet = new Set(selectedTargets);
    copyDayTargetSelect.innerHTML = DAY_LABELS.map((label, idx) => {
      const disabled = idx === sourceDay;
      const selected = !disabled && targetSet.has(idx);
      return `<option value="${idx}" ${disabled ? "disabled" : ""} ${selected ? "selected" : ""}>${label}</option>`;
    }).join("");
  }
}

function populateZoneCopyOptions(activeZone, selectedTargets = []) {
  if (!copyZonesSelect) return;
  const selectedSet = new Set(selectedTargets);
  const zoneOptions = ZONE_CHOICES.filter((zone) => zone.zone !== activeZone).sort((a, b) => {
    const labelA = (a.room ?? a.zone).toUpperCase();
    const labelB = (b.room ?? b.zone).toUpperCase();
    if (labelA < labelB) return -1;
    if (labelA > labelB) return 1;
    return 0;
  });
  copyZonesSelect.innerHTML = zoneOptions
    .map((zone) => {
      const selected = selectedSet.has(zone.zone);
      return `<option value="${zone.zone}" ${selected ? "selected" : ""}>${zone.room ?? zone.zone}</option>`;
    })
    .join("");
}

function canonicalizeEntries(entries) {
  return entries.map((entry) => {
    const normalized = normaliseScheduleEntry(entry);
    let setpoint = Number.parseFloat(normalized.setpoint);
    if (Number.isNaN(setpoint)) setpoint = 68;
    return {
      day_of_week: normalized.day,
      start_time: normalized.start,
      end_time: normalized.end,
      setpoint_f: setpoint,
      enabled: Boolean(normalized.enabled),
    };
  });
}

async function refreshPresetOptions(selectedId) {
  try {
    presetsCache = await fetchJson(`${API_BASE}/schedule/presets`);
    presetsLoaded = true;
  } catch (error) {
    console.error("Failed to load presets", error);
    presetsCache = [];
    presetsLoaded = false;
  }
  populatePresetSelect(selectedId);
}

function populatePresetSelect(selectedId) {
  if (!presetSelect) return;
  const options = presetsCache
    .map((preset) => {
      const selected = selectedId && Number(selectedId) === preset.Id;
      return `<option value="${preset.Id}" ${selected ? "selected" : ""}>${preset.Name}</option>`;
    })
    .join("");
  presetSelect.innerHTML = `<option value="">Choose preset…</option>${options}`;
  if (selectedId) {
    presetSelect.value = String(selectedId);
  }
}

function createScheduleRow(entry) {
  if (!scheduleTableBody) return;
  const tr = document.createElement("tr");
  const safeStart = entry.start.padStart(5, "0").slice(0, 5);
  const safeEnd = entry.end.padStart(5, "0").slice(0, 5);
  tr.innerHTML = `
    <td>
      <select class="schedule-day">
        ${DAY_LABELS.map(
    (label, idx) => `<option value="${idx}" ${idx === entry.day ? "selected" : ""}>${label}</option>`
  ).join("")}
      </select>
    </td>
    <td><input class="schedule-start" type="time" value="${safeStart}" /></td>
    <td><input class="schedule-end" type="time" value="${safeEnd}" /></td>
    <td><input class="schedule-setpoint" type="number" min="40" max="90" step="0.5" value="${Number.isFinite(entry.setpoint) ? entry.setpoint : 68}" /></td>
    <td><input class="schedule-enabled" type="checkbox" ${entry.enabled ? "checked" : ""} /></td>
    <td><button class="remove-row" type="button" aria-label="Remove window">&times;</button></td>
  `;
  scheduleTableBody.appendChild(tr);
}

function renderScheduleEntries(entries, { markClean = false } = {}) {
  if (!scheduleModal || !scheduleTableBody || !scheduleEmptyEl) return;

  const currentSource = copyDaySourceSelect
    ? Number.parseInt(copyDaySourceSelect.value, 10)
    : undefined;
  const currentTargets = copyDayTargetSelect
    ? Array.from(copyDayTargetSelect.selectedOptions)
      .map((opt) => Number.parseInt(opt.value, 10))
      .filter((value) => !Number.isNaN(value))
    : [];
  const currentZoneTargets = copyZonesSelect
    ? Array.from(copyZonesSelect.selectedOptions).map((opt) => opt.value)
    : [];

  const canonical = sortScheduleEntries(entries);
  scheduleTableBody.innerHTML = "";
  if (!canonical.length) {
    scheduleModal.classList.add("empty");
    scheduleEmptyEl.textContent = "No schedule defined yet.";
  } else {
    scheduleModal.classList.remove("empty");
    scheduleEmptyEl.textContent = "";
    canonical.forEach((entry) =>
      createScheduleRow({
        day: entry.day_of_week,
        start: entry.start_time,
        end: entry.end_time,
        setpoint: entry.setpoint_f,
        enabled: entry.enabled,
      })
    );
  }

  populateDaySelectors(currentSource, currentTargets);
  populateZoneCopyOptions(isGlobalSchedule ? null : activeScheduleZone, currentZoneTargets);

  if (markClean) {
    originalScheduleSnapshot = JSON.stringify(canonical);
    scheduleDirty = false;
    resetScheduleMessage();
  } else {
    scheduleDirty = true;
  }
}

function closeScheduleModal() {
  if (!scheduleModal) return;
  scheduleModal.classList.remove("open");
  scheduleModal.classList.remove("empty");
  scheduleModal.setAttribute("aria-hidden", "true");
  activeScheduleZone = null;
  isGlobalSchedule = false;
  originalScheduleSnapshot = "[]";
  scheduleDirty = false;
  resetScheduleMessage();
  if (scheduleTableBody) scheduleTableBody.innerHTML = "";
  scheduleEmptyEl && (scheduleEmptyEl.textContent = "No schedule defined yet.");
}

async function openScheduleModal(zoneName, roomLabel, options = {}) {
  if (!scheduleModal || !scheduleTableBody) return;
  const isGlobal = Boolean(options.isGlobal);
  isGlobalSchedule = isGlobal;
  scheduleModal.classList.toggle("global-mode", isGlobalSchedule);
  activeScheduleZone = isGlobalSchedule ? "__GLOBAL__" : zoneName;
  if (scheduleZoneLabel) {
    const label = isGlobalSchedule
      ? "Global Default Schedule"
      : roomLabel
        ? `${roomLabel} (${zoneName})`
        : zoneName;
    scheduleZoneLabel.textContent = label;
  }

  resetScheduleMessage();
  scheduleDirty = false;
  originalScheduleSnapshot = "[]";
  scheduleEmptyEl && (scheduleEmptyEl.textContent = "Loading schedule…");
  scheduleModal.classList.add("empty");
  scheduleTableBody.innerHTML = "";
  scheduleModal.classList.add("open");
  scheduleModal.setAttribute("aria-hidden", "false");

  populateDaySelectors();
  populateZoneCopyOptions(isGlobalSchedule ? null : zoneName);
  if (!presetsLoaded) {
    await refreshPresetOptions();
  } else {
    populatePresetSelect();
  }

  try {
    const endpoint = isGlobalSchedule
      ? `${API_BASE}/schedule/default`
      : `${API_BASE}/zones/${zoneName}/schedule`;
    const entries = await fetchJson(endpoint);
    renderScheduleEntries(entries, { markClean: true });
    if (isGlobalSchedule && scheduleInfo) {
      scheduleInfo.textContent =
        "Define the default heating windows applied when a zone has no custom schedule.";
    } else if (scheduleInfo) {
      scheduleInfo.textContent = "Define heating windows for this zone. Times use 24-hour format.";
    }
  } catch (error) {
    console.error("Failed to load schedule", error);
    showScheduleError("Unable to load schedule.");
    if (scheduleModal) {
      scheduleModal.classList.add("empty");
    }
    if (scheduleEmptyEl) {
      scheduleEmptyEl.textContent = "Unable to load schedule.";
    }
    scheduleDirty = false;
    originalScheduleSnapshot = "[]";
  }
}

function collectScheduleEntries({ silent = false } = {}) {
  if (!scheduleTableBody) return [];
  const rows = Array.from(scheduleTableBody.querySelectorAll("tr"));
  const entries = [];
  let valid = true;
  const seen = new Set();
  let duplicateConflict = false;
  rows.forEach((row) => {
    const day = Number.parseInt(row.querySelector(".schedule-day").value, 10);
    const start = row.querySelector(".schedule-start").value;
    const end = row.querySelector(".schedule-end").value;
    const setpoint = Number.parseFloat(row.querySelector(".schedule-setpoint").value);
    const enabled = row.querySelector(".schedule-enabled").checked;

    if (!start || !end || Number.isNaN(setpoint)) {
      valid = false;
      return;
    }
    const key = `${day}:${start}`;
    if (seen.has(key)) {
      valid = false;
      duplicateConflict = true;
      return;
    }
    seen.add(key);
    entries.push({
      day_of_week: day,
      start_time: start,
      end_time: end,
      setpoint_f: setpoint,
      enabled,
    });
  });

  if (!valid) {
    if (!silent) {
      showScheduleError(
        duplicateConflict
          ? "Each day can only have one window per start time."
          : "Please complete all schedule fields before saving."
      );
    }
    return null;
  }

  return entries;
}

function sortScheduleEntries(entries) {
  return canonicalizeEntries(entries)
    .sort((a, b) => {
      if (a.day_of_week !== b.day_of_week) {
        return a.day_of_week - b.day_of_week;
      }
      return a.start_time.localeCompare(b.start_time);
    });
}

function hasScheduleChanges() {
  if (!scheduleDirty) return false;
  const entries = collectScheduleEntries({ silent: true });
  if (entries === null) {
    return true;
  }
  const snapshot = JSON.stringify(sortScheduleEntries(entries));
  const changed = snapshot !== originalScheduleSnapshot;
  if (!changed) {
    scheduleDirty = false;
  }
  return changed;
}

function attemptCloseScheduleModal() {
  if (!scheduleModal || scheduleModal.getAttribute("aria-hidden") === "true") {
    return;
  }
  if (hasScheduleChanges()) {
    const confirmClose = window.confirm(
      "You have unsaved schedule changes. Close without saving?"
    );
    if (!confirmClose) {
      return;
    }
  }
  closeScheduleModal();
}

async function openGlobalScheduleManager() {
  if (!scheduleModal) return;
  if (scheduleModal.classList.contains("open") && !isGlobalSchedule) {
    if (hasScheduleChanges()) {
      const proceed = window.confirm(
        "You have unsaved schedule changes. Discard them and edit the global schedule?"
      );
      if (!proceed) {
        return;
      }
    }
    closeScheduleModal();
  }
  await openScheduleModal("GLOBAL", "Global", { isGlobal: true });
}

// Update a single table row in-place with new data from the API.
function updateZoneRow(row, zone) {
  const zoneName = getProp(zone, "zone_name", "ZoneName", "zoneName");
  const isSpecial = zoneName === "Z14";

  // Store current values as fallback in case new data is incomplete
  const currentRoomTemp = row.querySelector(".room").textContent;
  const currentPipeTemp = row.querySelector(".pipe").textContent;
  const currentSetpoint = row.querySelector(".setpoint-input")?.value;
  const currentDate = row.querySelector(".updated-date").textContent;
  const currentTime = row.querySelector(".updated-time").textContent;

  const currentState = getProp(zone, "current_state", "CurrentState", "currentState") ?? "—";
  row.dataset.state = currentState;
  row.classList.toggle("state-on", currentState === "ON");
  row.querySelector(".state").textContent = currentState;

  const roomName = getProp(zone, "room_name", "RoomName", "roomName");
  if (roomName) {
    row.querySelector(".room-label").textContent = roomName;
  }

  const roomTemp = getProp(zone, "zone_room_temp_f", "ZoneRoomTemp_F", "zoneRoomTempF");
  const formattedRoomTemp = isSpecial ? "—" : formatTemp(roomTemp);
  // Only update if we have valid data or if current shows "—"
  if (formattedRoomTemp && formattedRoomTemp !== "—" || currentRoomTemp === "—") {
    row.querySelector(".room").textContent = formattedRoomTemp;
  }

  const pipeTemp = getProp(zone, "pipe_temp_f", "PipeTemp_F", "pipeTempF");
  const formattedPipeTemp = formatTemp(pipeTemp);
  // Only update if we have valid data or if current shows "—"
  if (formattedPipeTemp && formattedPipeTemp !== "—" || currentPipeTemp === "—") {
    row.querySelector(".pipe").textContent = formattedPipeTemp;
  }

  const setpointValue = getProp(zone, "target_setpoint_f", "TargetSetpoint_F", "targetSetpointF");
  const controlModeRaw = getProp(zone, "control_mode", "ControlMode", "controlMode");
  const controlMode = controlModeRaw ? String(controlModeRaw).toUpperCase() : "";
  const setpointInput = row.querySelector(".setpoint-input");

  if (setpointInput) {
    // Check if user is actively editing OR if this field was just saved
    const isActive = document.activeElement === setpointInput;
    const justSaved = setpointInput.dataset.justSaved === 'true';

    // Check if this zone was recently overridden
    const recentOverrideTime = recentOverrides.get(zoneName);
    const isRecentlyOverridden = recentOverrideTime && (Date.now() - recentOverrideTime) < 30000; // 30 seconds

    if (!isActive && !justSaved && !isRecentlyOverridden) {
      // Show '-' if not in AUTO mode (THERMOSTAT, MANUAL, ON, OFF should all show dash)
      if (controlMode !== "AUTO") {
        setpointInput.value = "";
        setpointInput.placeholder = "—";
        setpointInput.disabled = true;

        // Also disable the save button for non-editable modes
        const saveButton = row.querySelector(".setpoint-save");
        if (saveButton) {
          saveButton.disabled = true;
        }
      } else {
        // Enable input only for AUTO mode
        setpointInput.disabled = false;

        // Also enable the save button for editable modes
        const saveButton = row.querySelector(".setpoint-save");
        if (saveButton) {
          saveButton.disabled = false;
        }

        // Only update if user isn't actively editing and didn't just save
        if (setpointValue === null || setpointValue === undefined) {
          // Only clear if we don't have a current valid value
          if (!currentSetpoint || currentSetpoint === "" || currentSetpoint === "—") {
            setpointInput.value = "";
            setpointInput.placeholder = "—";
          } else {
            // Keep the current setpoint value instead of clearing
          }
        } else {
          const formatted = Number.parseFloat(setpointValue).toFixed(1);
          setpointInput.value = formatted;
        }
      }
    } else if (justSaved) {
      // Skip update, field was just saved
    } else {
      // Skip update, field has focus
    }
  }
  const setpointPlaceholder = row.querySelector(".setpoint-placeholder");
  if (setpointPlaceholder) {
    setpointPlaceholder.textContent = "—";
  }

  const modeLabel = controlMode === "THERMOSTAT" ? "T-STAT" : controlMode;
  row.querySelector(".mode").textContent = modeLabel || "—";

  const isoTimestamp = getProp(zone, "updated_at", "UpdatedAt", "updatedAt") ?? "";
  const [fallbackDate, fallbackTime] = splitTimestamp(isoTimestamp);
  const datePart = getProp(zone, "updated_date", "UpdatedDate", "updatedDate") ?? fallbackDate;
  const timePartRaw = getProp(zone, "updated_time", "UpdatedTime", "updatedTime") ?? fallbackTime;

  // Convert UTC timestamp to local time for display
  const { date: localDate, time: localTime } = convertUTCToLocal(datePart, timePartRaw);

  // Only update date/time if we have new data or current shows "—"
  const newDate = localDate || "—";
  const newTime = localTime ? formatTime(localTime) : "—";

  if (newDate && newDate !== "—" || currentDate === "—") {
    row.querySelector(".updated-date").textContent = newDate;
  }
  if (newTime && newTime !== "—" || currentTime === "—") {
    row.querySelector(".updated-time").textContent = newTime;
  }

  const onBtn = row.querySelector('button[data-action="FORCE_ON"]');
  const offBtn = row.querySelector('button[data-action="FORCE_OFF"]');
  const autoBtn = row.querySelector('button[data-action="AUTO"]');
  const tstatBtn = row.querySelector('button[data-action="THERMOSTAT"]');
  [onBtn, offBtn, autoBtn, tstatBtn].forEach((btn) => btn && btn.classList.remove("active"));
  if (controlMode === "AUTO") {
    autoBtn && autoBtn.classList.add("active");
  } else if (controlMode === "THERMOSTAT") {
    tstatBtn && tstatBtn.classList.add("active");
  } else {
    if (currentState === "ON") {
      onBtn && onBtn.classList.add("active");
    } else {
      offBtn && offBtn.classList.add("active");
    }
  }
}

// Pull the latest status for every zone and update the table.
async function refreshZones() {
  try {
    if (DASHBOARD_CACHE_DEBUG) {
      console.info("[dashboard] refreshZones() starting");
    }
    const fetchStart = performance.now();
    const [zones, system] = await Promise.all([
      fetchJson(`${API_BASE}/zones`),
      fetchJson(`${API_BASE}/system`),
    ]);
    renderZones(zones);
    renderSystemStatusData(system);
    updateZonesCache({ zones, system });
    updatePiStatus(true);
    if (DASHBOARD_CACHE_DEBUG) {
      console.info("[dashboard] refreshZones() completed", {
        zones: zones.length,
        durationMs: (performance.now() - fetchStart).toFixed(1),
      });
    }
  } catch (error) {
    console.error("Failed to refresh zones", error);
    updatePiStatus(false);
  }
}

// Update Pi connection status indicator
function updatePiStatus(isOnline) {
  if (!piStatusEl) return;
  
  if (isOnline) {
    piStatusEl.classList.add('status-online');
    piStatusEl.classList.remove('status-offline');
  } else {
    piStatusEl.classList.add('status-offline');
    piStatusEl.classList.remove('status-online');
  }
}

// Refresh the outdoor temperature and timestamp in the summary card.
async function refreshSystemStatus() {
  if (!outsideTempEl && !systemUpdatedEl) return;
  try {
    const fetchStart = performance.now();
    const system = await fetchJson(`${API_BASE}/system`);
    renderSystemStatusData(system);
    updateZonesCache({ system });
    if (DASHBOARD_CACHE_DEBUG) {
      console.info("[dashboard] refreshSystemStatus() completed", {
        durationMs: (performance.now() - fetchStart).toFixed(1),
      });
    }
  } catch (error) {
    console.error("Failed to refresh system status", error);
  }
}

async function refreshStats() {
  if (!statsTableBody) return;
  try {
    const params = new URLSearchParams();
    const windowValue = statsWindowSelect ? statsWindowSelect.value : "day";
    params.set("window", windowValue);
    const dayValue = statsDayInput?.value;
    if (dayValue) {
      params.set("day", dayValue);
    }
    const fetchStart = performance.now();
    const stats = await fetchJson(`${API_BASE}/zones/stats?${params.toString()}`);
    renderStats(stats, { windowValue, dayValue });
    writeDashboardCache(DASHBOARD_STATS_CACHE_KEY, { stats, windowValue, dayValue });
    if (DASHBOARD_CACHE_DEBUG) {
      console.info("[dashboard] refreshStats() completed", {
        rows: stats.length,
        windowValue,
        dayValue,
        durationMs: (performance.now() - fetchStart).toFixed(1),
      });
    }
  } catch (error) {
    console.error("Failed to refresh stats", error);
    if (statsSummaryLabel) {
      statsSummaryLabel.textContent = "Unable to load statistics.";
    }
  }
}

// Fetch the most recent history entries and rebuild the list UI.
async function refreshEvents() {
  if (!eventsTableBody) return;
  try {
    const fetchStart = performance.now();
    const events = await fetchJson(`${API_BASE}/events?limit=40`);
    renderEvents(events);
    writeDashboardCache(DASHBOARD_EVENTS_CACHE_KEY, { events });
    if (DASHBOARD_CACHE_DEBUG) {
      console.info("[dashboard] refreshEvents() completed", {
        rows: events.length,
        durationMs: (performance.now() - fetchStart).toFixed(1),
      });
    }
  } catch (error) {
    console.error("Failed to refresh events", error);
  }
}

if (scheduleModal) {
  scheduleModal.addEventListener("click", (event) => {
    if (event.target === scheduleModal) {
      attemptCloseScheduleModal();
    }
  });
}

if (addScheduleRowBtn) {
  addScheduleRowBtn.addEventListener("click", () => {
    if (!scheduleModal) return;
    scheduleModal.classList.remove("empty");
    const now = new Date();
    const jsDay = now.getDay(); // Sunday=0
    const defaultDay = (jsDay + 6) % 7; // Monday=0
    createScheduleRow({ day: defaultDay, start: "06:00", end: "08:00", setpoint: 68, enabled: true });
    if (scheduleEmptyEl) scheduleEmptyEl.textContent = "";
    resetScheduleMessage();
    scheduleDirty = true;
  });
}

if (scheduleTableBody) {
  scheduleTableBody.addEventListener("click", (event) => {
    const removeBtn = event.target.closest(".remove-row");
    if (!removeBtn) return;
    const row = removeBtn.closest("tr");
    if (row) row.remove();
    if (!scheduleTableBody.querySelector("tr")) {
      if (scheduleModal) scheduleModal.classList.add("empty");
      if (scheduleEmptyEl) scheduleEmptyEl.textContent = "No schedule defined yet.";
    }
    resetScheduleMessage();
    scheduleDirty = true;
  });

  scheduleTableBody.addEventListener("input", (event) => {
    if (
      event.target.matches(
        ".schedule-start, .schedule-end, .schedule-setpoint"
      )
    ) {
      scheduleDirty = true;
      resetScheduleMessage();
    }
  });

  scheduleTableBody.addEventListener("change", (event) => {
    if (event.target.matches(".schedule-day, .schedule-enabled")) {
      scheduleDirty = true;
      resetScheduleMessage();
    }
  });
}

[cancelScheduleBtn, closeScheduleBtn].forEach((btn) => {
  if (btn) {
    btn.addEventListener("click", () => {
      attemptCloseScheduleModal();
    });
  }
});

if (openGlobalScheduleBtn) {
  openGlobalScheduleBtn.addEventListener("click", () => {
    openGlobalScheduleManager();
  });
}

if (openSchedulerViewBtn) {
  openSchedulerViewBtn.addEventListener("click", () => {
    window.location.href = "/scheduler";
  });
}

if (useGlobalForAutoBtn) {
  useGlobalForAutoBtn.addEventListener("click", async () => {
    const confirmApply = window.confirm(
      "Clear schedules for all AUTO zones so they follow the global default?"
    );
    if (!confirmApply) {
      return;
    }
    const originalLabel = useGlobalForAutoBtn.textContent;
    useGlobalForAutoBtn.disabled = true;
    try {
      const updatedZones = await fetchJson(`${API_BASE}/schedule/apply-global`, {
        method: "POST",
      });
      await refreshZones();
      if (Array.isArray(updatedZones) && updatedZones.length) {
        useGlobalForAutoBtn.textContent = `Applied (${updatedZones.length})`;
      } else {
        useGlobalForAutoBtn.textContent = "No AUTO zones";
      }
      setTimeout(() => {
        useGlobalForAutoBtn.textContent = originalLabel;
      }, 2500);
    } catch (error) {
      console.error("Failed to apply global schedule to AUTO zones", error);
      window.alert("Unable to apply the global schedule. Please try again.");
      useGlobalForAutoBtn.textContent = originalLabel;
    } finally {
      useGlobalForAutoBtn.disabled = false;
    }
  });
}

function getValidatedSetpoint(inputEl, label) {
  if (!inputEl) return null;
  const value = Number.parseFloat(inputEl.value);
  if (Number.isNaN(value)) {
    window.alert(`Enter a numeric temperature for ${label}.`);
    inputEl.focus();
    return null;
  }
  return value;
}

function applyZoneSnapshot(zones) {
  if (!Array.isArray(zones) || !zonesTable) return;
  zones.forEach((zone) => {
    const zoneName = getProp(zone, "zone_name", "ZoneName", "zoneName");
    if (!zoneName) return;
    const row = zonesTable.querySelector(`tr[data-zone="${zoneName}"]`);
    if (row) {
      updateZoneRow(row, zone);
    }
  });
}

function buildSchedulerGrid() {
  if (!schedulerTimeRow || !schedulerBody) return;
  const slotLabels = Array.from({ length: SCHEDULER_SLOTS }, (_, index) => {
    const hour = Math.floor(index / 2);
    const minutes = index % 2 === 0 ? "00" : "30";
    return `${hour.toString().padStart(2, "0")}:${minutes}`;
  });

  schedulerTimeRow.innerHTML = slotLabels
    .map((label, index) => {
      const majorTick = index % 2 === 0;
      return `<div class="time-cell" data-slot="${index}">${majorTick ? label : ""
        }</div>`;
    })
    .join("");

  schedulerBody.innerHTML = "";
  SCHEDULER_DAYS.forEach((day, dayIndex) => {
    const row = document.createElement("div");
    row.className = "scheduler-row";
    row.dataset.day = dayIndex;
    const slotsHtml = Array.from({ length: SCHEDULER_SLOTS })
      .map(
        (_, index) => `<div class="slot" data-slot="${index}"></div>`
      )
      .join("");
    row.innerHTML = `
      <div class="scheduler-day-label">${day}</div>
      <div class="scheduler-slot-row">
        ${slotsHtml}
        <div class="scheduler-bubble-layer"></div>
      </div>
    `;
    schedulerBody.appendChild(row);
  });
}

function getTempBand(temp) {
  const numTemp = Number(temp);
  if (numTemp > 70) return "WARM";
  if (numTemp < 60) return "COOL";
  return "NEUTRAL";
}

function getZoneState(zone) {
  return schedulerState[zone];
}

function cloneEntries(entries) {
  return entries.map((entry) => ({ ...entry }));
}

function ensureZoneState(zone) {
  if (!schedulerState[zone]) {
    schedulerState[zone] = {
      entries: [],
      originalEntries: [],
      dirty: false,
      usingGlobal: false,
      previewActive: false,
      previewBackup: null,
    };
  }
  return schedulerState[zone];
}

function markSchedulerDirty(zone, dirty = true) {
  const state = ensureZoneState(zone);
  state.dirty = dirty;
  if (dirty) {
    state.usingGlobal = false;
  }
  updateSchedulerControls();
}

function updateSchedulerControls() {
  if (!schedulerZoneSelect) return;
  const zone = schedulerZoneSelect.value;
  const state = schedulerState[zone];
  const dirty = state?.dirty ?? false;
  if (schedulerSaveBtn) schedulerSaveBtn.disabled = !dirty;
  if (schedulerResetBtn) schedulerResetBtn.disabled = !dirty;
}

function populateSchedulerDayControls() {
  if (!schedulerCopyDaySource || !schedulerCopyDayTargets) return;
  schedulerCopyDaySource.innerHTML = SCHEDULER_DAYS.map(
    (label, index) => `<option value="${index}">${label}</option>`
  ).join("");
  schedulerCopyDayTargets.innerHTML = SCHEDULER_DAYS.map(
    (label, index) => `<option value="${index}">${label}</option>`
  ).join("");
  schedulerCopyDayTargets.scrollTop = 0;
}

function updateCopyDayTargetsDisabled() {
  if (!schedulerCopyDaySource || !schedulerCopyDayTargets) return;
  const source = Number(schedulerCopyDaySource.value ?? 0);
  Array.from(schedulerCopyDayTargets.options).forEach((option) => {
    option.disabled = Number(option.value) === source;
  });
}

function populateSchedulerZoneTargetsSelect() {
  if (!schedulerCopyZoneTargets || !schedulerZoneSelect) return;
  const currentZone = schedulerZoneSelect.value;
  schedulerCopyZoneTargets.innerHTML = ZONE_CHOICES.filter(
    (zone) => zone.zone !== currentZone
  )
    .map(
      (zone) =>
        `<option value="${zone.zone}">${zone.room ?? zone.zone}</option>`
    )
    .join("");
}

async function loadSchedulerPresets(selectedId) {
  if (!schedulerPresetSelect) return;
  try {
    const presets = await fetchJson(`${API_BASE}/schedule/presets`);
    schedulerPresetSelect.innerHTML = `
      <option value="">Select preset</option>
      ${presets
        .map(
          (preset) =>
            `<option value="${preset.Id ?? preset.id}">${preset.Name ?? preset.name
            }</option>`
        )
        .join("")}
    `;
    if (selectedId) {
      schedulerPresetSelect.value = String(selectedId);
    }
  } catch (error) {
    console.error("Failed to load presets", error);
  }
}

function slotToTime(minutes) {
  const clamped = Math.max(0, Math.min(1439, minutes));
  const hour = Math.floor(clamped / 60);
  const minute = clamped % 60;
  return `${hour.toString().padStart(2, "0")}:${minute
    .toString()
    .padStart(2, "0")}`;
}

function timeStringToSlot(value) {
  const minutes = minutesFromTime(value);
  if (Number.isNaN(minutes)) return null;
  return Math.max(0, Math.min(SCHEDULER_SLOTS, Math.round(minutes / 30)));
}

function serializeSchedulerEntries(entries) {
  const serialized = entries
    .map((entry) => {
      const startMinutes = entry.start * 30;
      let endMinutes = startMinutes + entry.duration * 30;
      endMinutes = Math.min(24 * 60, endMinutes);
      if (endMinutes === 24 * 60) {
        endMinutes = 24 * 60 - 1;
      }
      return {
        day_of_week: gridDayToApiDay(entry.day),
        start_time: slotToTime(startMinutes),
        end_time: slotToTime(endMinutes),
        setpoint_f: entry.temp,
        enabled: true,
      };
    })
    .sort((a, b) => {
      if (a.day_of_week !== b.day_of_week) {
        return a.day_of_week - b.day_of_week;
      }
      return a.start_time.localeCompare(b.start_time);
    });
  return serialized;
}

function addSchedulerEntry(zone, day, slot, duration = 2, temp = 68) {
  const state = ensureZoneState(zone);
  const entry = {
    id: generateId(),
    day,
    start: Math.max(0, Math.min(SCHEDULER_SLOTS - duration, slot)),
    duration: Math.max(1, duration),
    temp,
  };
  state.entries.push(entry);
  markSchedulerDirty(zone);
  renderSchedulerBubbles(zone);
}

function resetSchedulerZone(zone) {
  const state = schedulerState[zone];
  if (!state) return;
  if (state.previewActive && state.previewBackup) {
    state.entries = cloneEntries(state.previewBackup);
    state.previewActive = false;
    state.previewBackup = null;
  } else {
    state.entries = cloneEntries(state.originalEntries);
    state.dirty = false;
  }
  renderSchedulerBubbles(zone);
  updateSchedulerControls();
  setSchedulerStatus("", null);
}

function copySchedulerDay(zone, sourceDay, targetDays) {
  const state = ensureZoneState(zone);
  const sourceEntries = state.entries.filter(
    (entry) => entry.day === sourceDay
  );
  if (!sourceEntries.length) {
    window.alert("Source day has no setpoints to copy.");
    return;
  }
  state.entries = state.entries.filter(
    (entry) => !targetDays.includes(entry.day)
  );
  targetDays.forEach((day) => {
    sourceEntries.forEach((entry) => {
      state.entries.push({
        ...entry,
        id: generateId(),
        day,
      });
    });
  });
  markSchedulerDirty(zone);
  renderSchedulerBubbles(zone);
}

async function fetchPresetDetail(presetId) {
  return fetchJson(`${API_BASE}/schedule/presets/${presetId}`);
}

async function previewPresetOnZone(zone, presetId) {
  if (!zone || !presetId) return;
  const state = ensureZoneState(zone);
  if (state.dirty) {
    const proceed = window.confirm(
      "Discard unsaved changes before previewing this preset?"
    );
    if (!proceed) {
      return;
    }
  }
  try {
    const preset = await fetchPresetDetail(presetId);
    const normalized = normalizeScheduleEntries(
      preset.entries ?? preset.Entries ?? []
    );
    state.previewBackup = cloneEntries(state.entries);
    state.previewActive = true;
    state.entries = normalized;
    state.dirty = false;
    state.usingGlobal = false;
    renderSchedulerBubbles(zone);
    updateSchedulerControls();
    setSchedulerStatus(
      `Previewing preset "${preset.Name ?? preset.name}". Save to apply or Reset to cancel.`,
      null
    );
  } catch (error) {
    console.error("Failed to preview preset", error);
    window.alert("Unable to preview preset.");
  }
}

async function applyPresetGlobally(presetId) {
  if (!presetId) {
    window.alert("Select a preset first.");
    return;
  }
  const confirmApply = window.confirm(
    "Apply this preset to all zones? This will replace each zone's schedule."
  );
  if (!confirmApply) return;
  try {
    const preset = await fetchPresetDetail(presetId);
    const normalized = normalizeScheduleEntries(
      preset.entries ?? preset.Entries ?? []
    );
    const payload = {
      entries: serializeSchedulerEntries(normalized),
    };
    for (const zoneObj of ZONE_CHOICES) {
      const zoneName = zoneObj.zone;
      await fetchJson(`${API_BASE}/zones/${zoneName}/schedule`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }
    window.alert("Preset applied to all zones.");
    if (schedulerZoneSelect) {
      loadSchedulerData(schedulerZoneSelect.value);
    }
    refreshZones();
  } catch (error) {
    console.error("Failed to apply preset globally", error);
    window.alert("Failed to apply preset globally.");
  }
}

async function saveSchedulerZone(zone) {
  if (!zone) return;
  const state = schedulerState[zone];
  if (!state || !state.dirty) return;
  setSchedulerStatus("Saving…", "loading");
  if (schedulerSaveBtn) schedulerSaveBtn.disabled = true;
  try {
    const payload = {
      entries: serializeSchedulerEntries(state.entries),
    };
    const updated = await fetchJson(
      `${API_BASE}/zones/${zone}/schedule`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    );
    const normalized = normalizeScheduleEntries(updated);
    state.entries = normalized;
    state.originalEntries = cloneEntries(normalized);
    state.dirty = false;
    state.usingGlobal = false;
    renderSchedulerBubbles(zone);
    setSchedulerStatus("", null);
    refreshZones();
  } catch (error) {
    console.error("Failed to save schedule", error);
    setSchedulerStatus(
      error?.message ?? "Failed to save schedule.",
      "error"
    );
  } finally {
    updateSchedulerControls();
  }
}

async function copyScheduleToZones(zone, targets) {
  if (!zone || !targets.length) return;
  try {
    await fetchJson(`${API_BASE}/zones/${zone}/schedule/clone`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_zones: targets }),
    });
    window.alert(`Copied schedule to ${targets.length} zone(s).`);
  } catch (error) {
    console.error("Failed to copy schedule to zones", error);
    window.alert("Failed to copy schedule to selected zones.");
  }
}

function renderSchedulerBubbles(zone) {
  if (!schedulerBody) return;
  const state = schedulerState[zone];
  if (!state) return;
  const data = state.entries ?? [];
  schedulerBody
    .querySelectorAll(".scheduler-bubble-layer")
    .forEach((layer) => (layer.innerHTML = ""));

  if (!data.length && schedulerStatusNote) {
    schedulerStatusNote.textContent =
      "No schedule defined for this zone (showing defaults). Click a slot to add one.";
  } else if (schedulerStatusNote) {
    schedulerStatusNote.textContent =
      state.usingGlobal
        ? "Showing global default schedule. Edit and Save to customize this zone."
        : "Drag bubbles or click slots to edit the weekly schedule. Remember to Save.";
  }

  data.forEach((entry) => {
    const row = schedulerBody.querySelector(`.scheduler-row[data-day="${entry.day}"]`);
    if (!row) return;
    const layer = row.querySelector(".scheduler-bubble-layer");
    if (!layer) return;
    const bubble = document.createElement("div");
    const leftPercent = (entry.start / SCHEDULER_SLOTS) * 100;
    const widthPercent = (entry.duration / SCHEDULER_SLOTS) * 100;
    bubble.className = "scheduler-bubble";
    bubble.dataset.id = entry.id;
    bubble.dataset.day = entry.day;
    bubble.dataset.temp = getTempBand(entry.temp);
    bubble.style.left = `${leftPercent}%`;
    bubble.style.width = `${widthPercent}%`;
    bubble.innerHTML = `
      <div class="resize-handle left" data-direction="left"></div>
      <span class="temp-label">${entry.temp.toFixed(0)}°</span>
      <div class="resize-handle right" data-direction="right"></div>
    `;
    bubble.addEventListener("click", (event) => {
      if (activeBubbleDrag) return;
      event.stopPropagation();
      openBubbleEditor(bubble, entry, zone);
    });
    bubble.querySelectorAll(".resize-handle").forEach((handle) => {
      handle.addEventListener("pointerdown", (event) => {
        event.stopPropagation();
        attachResizeHandler(event, bubble, entry, zone, handle.dataset.direction);
      });
    });
    attachBubbleDragHandlers(bubble, entry, zone);
    layer.appendChild(bubble);
  });
  updateSchedulerControls();
}

function initializeScheduler() {
  if (!schedulerZoneSelect || !schedulerTimeRow || !schedulerBody) return;
  buildSchedulerGrid();
  const initialZone =
    schedulerZoneSelect.value || (ZONE_CHOICES[0] ? ZONE_CHOICES[0].zone : null);
  populateSchedulerDayControls();
  updateCopyDayTargetsDisabled();
  populateSchedulerZoneTargetsSelect();
  loadSchedulerPresets();
  if (initialZone) {
    if (!schedulerZoneSelect.value) {
      schedulerZoneSelect.value = initialZone;
    }
    loadSchedulerData(initialZone);
  }
  schedulerZoneSelect.addEventListener("change", (event) => {
    populateSchedulerZoneTargetsSelect();
    loadSchedulerData(event.target.value);
  });
  if (schedulerCopyDaySource) {
    schedulerCopyDaySource.addEventListener("change", () => {
      updateCopyDayTargetsDisabled();
    });
  }

  if (schedulerCopyDayBtn) {
    schedulerCopyDayBtn.addEventListener("click", () => {
      if (!schedulerZoneSelect) return;
      const zone = schedulerZoneSelect.value;
      const sourceDay = Number(schedulerCopyDaySource?.value ?? 0);
      const targetDays = Array.from(
        schedulerCopyDayTargets?.selectedOptions ?? []
      )
        .map((option) => Number(option.value))
        .filter((value) => value !== sourceDay);
      if (!targetDays.length) {
        window.alert("Select at least one target day.");
        return;
      }
      copySchedulerDay(zone, sourceDay, targetDays);
    });
  }

  if (schedulerCopyZoneBtn) {
    schedulerCopyZoneBtn.addEventListener("click", async () => {
      if (!schedulerZoneSelect) return;
      const zone = schedulerZoneSelect.value;
      const targets = Array.from(
        schedulerCopyZoneTargets?.selectedOptions ?? []
      ).map((option) => option.value);
      if (!targets.length) {
        window.alert("Select at least one zone to copy to.");
        return;
      }
      const state = schedulerState[zone];
      if (state?.dirty) {
        const confirmSave = window.confirm(
          "Save this zone's schedule before copying?"
        );
        if (!confirmSave) {
          return;
        }
        await saveSchedulerZone(zone);
      }
      await copyScheduleToZones(zone, targets);
    });
  }

  if (schedulerPresetApplyBtn) {
    schedulerPresetApplyBtn.addEventListener("click", () => {
      if (!schedulerZoneSelect) return;
      const presetId = schedulerPresetSelect?.value;
      if (!presetId) {
        window.alert("Select a preset to apply.");
        return;
      }
      applyPresetToZone(schedulerZoneSelect.value, presetId);
    });
  }

  if (schedulerPresetPreviewBtn) {
    schedulerPresetPreviewBtn.addEventListener("click", () => {
      if (!schedulerZoneSelect) return;
      const presetId = schedulerPresetSelect?.value;
      if (!presetId) {
        window.alert("Select a preset to preview.");
        return;
      }
      previewPresetOnZone(schedulerZoneSelect.value, presetId);
    });
  }

  if (schedulerPresetApplyGlobalBtn) {
    schedulerPresetApplyGlobalBtn.addEventListener("click", () => {
      const presetId = schedulerPresetSelect?.value;
      if (!presetId) {
        window.alert("Select a preset to apply.");
        return;
      }
      applyPresetGlobally(presetId);
    });
  }

  if (schedulerPresetSaveBtn) {
    schedulerPresetSaveBtn.addEventListener("click", () => {
      if (!schedulerZoneSelect) return;
      saveCurrentZoneAsPreset(schedulerZoneSelect.value);
    });
  }

  const schedulerPresetDeleteBtn = document.getElementById("schedulerPresetDeleteBtn");
  if (schedulerPresetDeleteBtn) {
    schedulerPresetDeleteBtn.addEventListener("click", async () => {
      if (!schedulerPresetSelect || !schedulerPresetSelect.value) {
        window.alert("Select a preset to delete.");
        return;
      }
      const id = Number.parseInt(schedulerPresetSelect.value, 10);
      if (Number.isNaN(id)) {
        window.alert("Invalid preset selection.");
        return;
      }
      const preset = presetsCache.find((p) => (p.Id ?? p.id) === id);
      const name = preset ? preset.Name ?? preset.name ?? "this preset" : "this preset";
      const confirmed = window.confirm(`Delete preset "${name}"? This cannot be undone.`);
      if (!confirmed) {
        return;
      }
      try {
        const response = await fetch(`${API_BASE}/schedule/presets/${id}`, {
          method: "DELETE",
        });
        if (!response.ok) {
          const text = await response.text();
          throw new Error(text || "Failed to delete preset");
        }
        await loadSchedulerPresets();
        window.alert("Preset deleted.");
      } catch (error) {
        console.error("Failed to delete preset", error);
        window.alert("Failed to delete preset: " + (error.message || error));
      }
    });
  }

  document.addEventListener("click", (event) => {
    if (
      activeBubbleEditor &&
      !activeBubbleEditor.contains(event.target) &&
      !event.target.classList.contains("scheduler-bubble")
    ) {
      closeBubbleEditor();
    }
  });

  schedulerBody.addEventListener("click", (event) => {
    const slotEl = event.target.closest(".slot");
    if (activeBubbleEditor) {
      closeBubbleEditor();
      return;
    }
    if (!slotEl || event.target.closest(".scheduler-bubble")) {
      return;
    }
    if (!schedulerZoneSelect) return;
    const zone = schedulerZoneSelect.value;
    if (!schedulerState[zone]) return;
    const rowEl = slotEl.closest(".scheduler-row");
    if (!rowEl) return;
    const day = Number(rowEl.dataset.day ?? 0);
    const slot = Number(slotEl.dataset.slot ?? 0);
    addSchedulerEntry(zone, day, slot);
  });

  if (schedulerAddBtn) {
    schedulerAddBtn.addEventListener("click", () => {
      if (!schedulerZoneSelect) return;
      addSchedulerEntry(schedulerZoneSelect.value, 0, 16);
    });
  }

  if (schedulerResetBtn) {
    schedulerResetBtn.addEventListener("click", () => {
      if (!schedulerZoneSelect) return;
      resetSchedulerZone(schedulerZoneSelect.value);
    });
  }

  if (schedulerSaveBtn) {
    schedulerSaveBtn.addEventListener("click", () => {
      if (!schedulerZoneSelect) return;
      saveSchedulerZone(schedulerZoneSelect.value);
    });
  }
}

function setSchedulerStatus(stateText, statusClass) {
  const targets = [schedulerGridWrapper, schedulerGrid].filter(Boolean);
  targets.forEach((target) => {
    target.classList.remove("loading", "error");
    if (statusClass) {
      target.classList.add(statusClass);
      target.setAttribute("data-status", stateText || "");
    } else {
      target.removeAttribute("data-status");
    }
  });
  if (schedulerStatusNote && stateText && statusClass === "error") {
    schedulerStatusNote.textContent = stateText;
  }
}

function minutesFromTime(timeStr) {
  if (!timeStr) return NaN;
  const [h, m] = timeStr.split(":").map((value) => Number.parseInt(value, 10));
  if (Number.isNaN(h) || Number.isNaN(m)) return NaN;
  return h * 60 + m;
}

function normalizeScheduleEntries(entries) {
  const normalized = [];
  entries.forEach((entry, idx) => {
    const apiDay = Number(entry.day_of_week ?? entry.DayOfWeek ?? 0);
    const temp = Number(entry.setpoint_f ?? entry.Setpoint_F ?? 68);
    const start = minutesFromTime(entry.start_time ?? entry.StartTime ?? "00:00");
    const end = minutesFromTime(entry.end_time ?? entry.EndTime ?? "00:00");
    if (
      Number.isNaN(apiDay) ||
      Number.isNaN(temp) ||
      Number.isNaN(start) ||
      Number.isNaN(end)
    ) {
      return;
    }
    const segments = splitEntryIntoSegments(apiDay, start, end);
    segments.forEach((segment, segmentIndex) => {
      normalized.push({
        id: `${entry.id ?? entry.Id ?? idx}-${segmentIndex}`,
        day: apiDayToGridDay(segment.day),
        start: segment.startSlot,
        duration: segment.durationSlots,
        temp,
      });
    });
  });
  return normalized;
}

function splitEntryIntoSegments(day, startMinutes, endMinutes) {
  const MINUTES_PER_DAY = 1440;
  const result = [];
  let startAbs = day * MINUTES_PER_DAY + startMinutes;
  let endAbs = day * MINUTES_PER_DAY + endMinutes;
  if (endAbs <= startAbs) {
    endAbs += MINUTES_PER_DAY;
  }
  while (startAbs < endAbs) {
    const currentDayIndex = Math.floor(startAbs / MINUTES_PER_DAY) % 7;
    const dayStartAbs = Math.floor(startAbs / MINUTES_PER_DAY) * MINUTES_PER_DAY;
    const dayEndAbs = dayStartAbs + MINUTES_PER_DAY;
    const segmentEndAbs = Math.min(dayEndAbs, endAbs);
    const localStart = startAbs - dayStartAbs;
    const localEnd = segmentEndAbs - dayStartAbs;
    const startSlot = Math.max(0, Math.floor(localStart / 30));
    const endSlot = Math.min(
      SCHEDULER_SLOTS,
      Math.max(startSlot + 1, Math.ceil(localEnd / 30))
    );
    result.push({
      day: currentDayIndex,
      startSlot,
      durationSlots: Math.max(1, endSlot - startSlot),
    });
    startAbs = segmentEndAbs;
  }
  return result;
}

async function loadSchedulerData(zone) {
  if (!zone) return;
  setSchedulerStatus("Loading…", "loading");
  try {
    let entries = await fetchJson(`${API_BASE}/zones/${zone}/schedule`);
    let usingGlobal = false;
    if (!entries.length) {
      try {
        entries = await fetchJson(`${API_BASE}/schedule/default`);
        usingGlobal = true;
      } catch (error) {
        console.warn("Failed to load global fallback schedule", error);
      }
    }
    const normalized = normalizeScheduleEntries(entries);
    schedulerState[zone] = {
      entries: normalized,
      originalEntries: cloneEntries(normalized),
      dirty: false,
      usingGlobal,
    };
    renderSchedulerBubbles(zone);
    setSchedulerStatus("", null);
  } catch (error) {
    console.error("Failed to load scheduler data", error);
    schedulerState[zone] = {
      entries: [],
      originalEntries: [],
      dirty: false,
      usingGlobal: false,
    };
    renderSchedulerBubbles(zone);
    setSchedulerStatus("Unable to load schedule", "error");
  }
  updateSchedulerControls();
}

function openBubbleEditor(bubbleEl, entry, zoneName) {
  closeBubbleEditor();
  const editor = document.createElement("div");
  editor.className = "scheduler-editor";
  const sliderId = `slider-${entry.id}`;
  const startId = `start-${entry.id}`;
  const endId = `end-${entry.id}`;
  const tempInputId = `temp-${entry.id}`;
  const startTime = slotToTime(entry.start * 30);
  const endTime = slotToTime((entry.start + entry.duration) * 30);
  editor.innerHTML = `
    <div class="temp-controls">
      <label for="${sliderId}">Temp</label>
      <div class="range-wrapper">
        <input id="${sliderId}" type="range" min="50" max="80" step="0.5" value="${entry.temp}">
      </div>
      <input id="${tempInputId}" class="temp-value" type="number" min="40" max="90" step="0.5" value="${entry.temp.toFixed(1)}">
    </div>
    <div class="time-inputs">
      <label for="${startId}">Start
        <input id="${startId}" type="time" step="1800" value="${startTime}">
      </label>
      <label for="${endId}">End
        <input id="${endId}" type="time" step="1800" value="${endTime}">
      </label>
    </div>
    <div class="editor-actions">
      <button type="button" class="primary" data-action="save">Save</button>
      <button type="button" data-action="delete">Delete</button>
      <button type="button" data-action="cancel">Cancel</button>
    </div>
  `;
  const slider = editor.querySelector(`#${sliderId}`);
  const tempInput = editor.querySelector(`#${tempInputId}`);
  const saveBtn = editor.querySelector('button[data-action="save"]');
  const cancelBtn = editor.querySelector('button[data-action="cancel"]');
  const deleteBtn = editor.querySelector('button[data-action="delete"]');
  const startInput = editor.querySelector(`#${startId}`);
  const endInput = editor.querySelector(`#${endId}`);
  ["pointerdown", "pointermove", "click"].forEach((evt) => {
    editor.addEventListener(evt, (event) => event.stopPropagation());
  });
  slider.addEventListener("input", (event) => {
    const value = Number.parseFloat(event.target.value);
    if (!Number.isNaN(value)) {
      tempInput.value = value.toFixed(1);
      bubbleEl.querySelector(".temp-label").textContent = `${value.toFixed(0)}°`;
      bubbleEl.dataset.temp = getTempBand(value);
    }
  });

  tempInput.addEventListener("input", (event) => {
    const value = Number.parseFloat(event.target.value);
    if (!Number.isNaN(value)) {
      slider.value = value;
      bubbleEl.querySelector(".temp-label").textContent = `${value.toFixed(0)}°`;
      bubbleEl.dataset.temp = getTempBand(value);
    }
  });

  saveBtn.addEventListener("click", () => {
    const newTemp = Number.parseFloat(tempInput.value);
    const startSlot = timeStringToSlot(startInput.value);
    const endSlot = timeStringToSlot(endInput.value);
    if (Number.isNaN(newTemp) || startSlot === null || endSlot === null) {
      window.alert("Enter valid temperature and times.");
      return;
    }
    if (endSlot <= startSlot) {
      window.alert("End time must be after start time.");
      return;
    }
    entry.temp = newTemp;
    entry.start = Math.max(0, Math.min(SCHEDULER_SLOTS - 1, startSlot));
    entry.duration = Math.max(
      1,
      Math.min(SCHEDULER_SLOTS - entry.start, endSlot - startSlot)
    );
    bubbleEl.querySelector(".temp-label").textContent = `${newTemp.toFixed(0)}°`;
    bubbleEl.dataset.temp = getTempBand(newTemp);
    markSchedulerDirty(zoneName);
    renderSchedulerBubbles(zoneName);
    closeBubbleEditor();
  });
  deleteBtn.addEventListener("click", () => {
    const zoneState = schedulerState[zoneName];
    if (!zoneState) return;
    zoneState.entries = zoneState.entries.filter((item) => item.id !== entry.id);
    markSchedulerDirty(zoneName);
    renderSchedulerBubbles(zoneName);
    closeBubbleEditor();
  });
  cancelBtn.addEventListener("click", () => closeBubbleEditor());
  document.body.appendChild(editor);
  positionBubbleEditor(editor, bubbleEl);
  activeBubbleEditor = editor;
}

function closeBubbleEditor() {
  if (activeBubbleEditor && activeBubbleEditor.parentElement) {
    activeBubbleEditor.parentElement.removeChild(activeBubbleEditor);
  }
  activeBubbleEditor = null;
}

function positionBubbleEditor(editor, bubbleEl) {
  const bubbleRect = bubbleEl.getBoundingClientRect();
  const editorRect = editor.getBoundingClientRect();
  let top = bubbleRect.top + window.scrollY - editorRect.height - 8;
  if (top < window.scrollY + 10) {
    top = bubbleRect.bottom + window.scrollY + 8;
  }
  let left = bubbleRect.left + window.scrollX;
  const maxLeft = window.scrollX + window.innerWidth - editorRect.width - 16;
  left = Math.max(window.scrollX + 16, Math.min(left, maxLeft));
  editor.style.top = `${top}px`;
  editor.style.left = `${left}px`;
}

function attachBubbleDragHandlers(bubbleEl, entry, zoneName) {
  bubbleEl.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    closeBubbleEditor();
    const slotRow = bubbleEl.closest(".scheduler-slot-row");
    const rowEl = bubbleEl.closest(".scheduler-row");
    if (!slotRow || !rowEl) return;
    const rowRect = slotRow.getBoundingClientRect();
    const rowHeight = rowEl.getBoundingClientRect().height;
    const slotWidth = rowRect.width / SCHEDULER_SLOTS;
    const pointerId = event.pointerId;
    bubbleEl.setPointerCapture(pointerId);
    activeBubbleDrag = {
      pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originalStart: entry.start,
      originalDay: entry.day,
      slotWidth,
      rowHeight,
      bubbleEl,
      entry,
      zoneName,
      changed: false,
    };
    bubbleEl.classList.add("dragging");
  });

  bubbleEl.addEventListener("pointermove", (event) => {
    if (!activeBubbleDrag || event.pointerId !== activeBubbleDrag.pointerId) {
      return;
    }
    event.preventDefault();
    const {
      startX,
      startY,
      originalStart,
      originalDay,
      slotWidth,
      rowHeight,
      entry: dragEntry,
      bubbleEl: dragBubble,
    } = activeBubbleDrag;

    const deltaX = event.clientX - startX;
    const slotOffset = Math.round(deltaX / slotWidth);
    let newStart = originalStart + slotOffset;
    newStart = Math.max(0, Math.min(SCHEDULER_SLOTS - dragEntry.duration, newStart));
    if (newStart !== dragEntry.start) {
      dragEntry.start = newStart;
      dragBubble.style.left = `${(newStart / SCHEDULER_SLOTS) * 100}%`;
      activeBubbleDrag.changed = true;
    }

    const deltaY = event.clientY - startY;
    const dayOffset = Math.round(deltaY / rowHeight);
    let newDay = originalDay + dayOffset;
    newDay = Math.max(0, Math.min(SCHEDULER_DAYS.length - 1, newDay));
    if (newDay !== dragEntry.day) {
      dragEntry.day = newDay;
      const targetLayer = schedulerBody?.querySelector(
        `.scheduler-row[data-day="${newDay}"] .scheduler-bubble-layer`
      );
      if (targetLayer) {
        targetLayer.appendChild(dragBubble);
      }
      activeBubbleDrag.changed = true;
    }
  });

  const finalizeDrag = () => {
    if (!activeBubbleDrag) return;
    activeBubbleDrag.bubbleEl.classList.remove("dragging");
    if (activeBubbleDrag.changed) {
      markSchedulerDirty(activeBubbleDrag.zoneName);
      renderSchedulerBubbles(activeBubbleDrag.zoneName);
    }
    activeBubbleDrag = null;
  };

  bubbleEl.addEventListener("pointerup", (event) => {
    if (activeBubbleDrag && event.pointerId === activeBubbleDrag.pointerId) {
      bubbleEl.releasePointerCapture(activeBubbleDrag.pointerId);
      finalizeDrag();
    }
  });
  bubbleEl.addEventListener("pointercancel", finalizeDrag);
}

function attachResizeHandler(event, bubbleEl, entry, zoneName, direction) {
  const slotRow = bubbleEl.closest(".scheduler-slot-row");
  if (!slotRow) return;
  const rowRect = slotRow.getBoundingClientRect();
  const slotWidth = rowRect.width / SCHEDULER_SLOTS;
  const pointerId = event.pointerId;
  bubbleEl.setPointerCapture(pointerId);
  const dragState = {
    pointerId,
    direction,
    startX: event.clientX,
    originalStart: entry.start,
    originalDuration: entry.duration,
    slotWidth,
    changed: false,
  };

  const handleMove = (moveEvent) => {
    if (moveEvent.pointerId !== pointerId) return;
    moveEvent.preventDefault();
    const deltaX = moveEvent.clientX - dragState.startX;
    const slotDelta = Math.round(deltaX / slotWidth);
    if (direction === "left") {
      let newStart = dragState.originalStart + slotDelta;
      let newDuration =
        dragState.originalDuration - slotDelta;
      if (newStart < 0) {
        newDuration += newStart;
        newStart = 0;
      }
      newDuration = Math.max(1, Math.min(SCHEDULER_SLOTS - newStart, newDuration));
      if (newStart !== entry.start || newDuration !== entry.duration) {
        entry.start = newStart;
        entry.duration = newDuration;
        dragState.changed = true;
        bubbleEl.style.left = `${(entry.start / SCHEDULER_SLOTS) * 100}%`;
        bubbleEl.style.width = `${(entry.duration / SCHEDULER_SLOTS) * 100}%`;
      }
    } else {
      let newDuration = dragState.originalDuration + slotDelta;
      newDuration = Math.max(1, Math.min(SCHEDULER_SLOTS - entry.start, newDuration));
      if (newDuration !== entry.duration) {
        entry.duration = newDuration;
        dragState.changed = true;
        bubbleEl.style.width = `${(entry.duration / SCHEDULER_SLOTS) * 100}%`;
      }
    }
  };

  const handleUp = (upEvent) => {
    if (upEvent.pointerId !== pointerId) return;
    bubbleEl.releasePointerCapture(pointerId);
    bubbleEl.removeEventListener("pointermove", handleMove);
    bubbleEl.removeEventListener("pointerup", handleUp);
    bubbleEl.removeEventListener("pointercancel", handleUp);
    if (dragState.changed) {
      markSchedulerDirty(zoneName);
      renderSchedulerBubbles(zoneName);
    }
  };

  bubbleEl.addEventListener("pointermove", handleMove);
  bubbleEl.addEventListener("pointerup", handleUp);
  bubbleEl.addEventListener("pointercancel", handleUp);
}

if (manageGlobalBtn) {
  manageGlobalBtn.addEventListener("click", () => {
    if (isGlobalSchedule) return;
    if (hasScheduleChanges()) {
      const proceed = window.confirm(
        "You have unsaved schedule changes. Discard them and edit the global schedule?"
      );
      if (!proceed) {
        return;
      }
    }
    closeScheduleModal();
    openGlobalScheduleManager();
  });
}

if (saveScheduleBtn) {
  saveScheduleBtn.addEventListener("click", async () => {
    if (!scheduleModal || scheduleModal.getAttribute("aria-hidden") === "true") {
      return;
    }
    if (!activeScheduleZone && !isGlobalSchedule) {
      closeScheduleModal();
      return;
    }
    const entries = collectScheduleEntries();
    if (entries === null) {
      return;
    }
    resetScheduleMessage();
    const sortedEntries = sortScheduleEntries(entries);
    try {
      if (isGlobalSchedule) {
        await fetchJson(`${API_BASE}/schedule/default`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ entries: sortedEntries }),
        });
        renderScheduleEntries(sortedEntries, { markClean: true });
        showScheduleSuccess("Global schedule saved.");
      } else {
        await fetchJson(`${API_BASE}/zones/${activeScheduleZone}/schedule`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ entries: sortedEntries }),
        });
        renderScheduleEntries(sortedEntries, { markClean: true });
        showScheduleSuccess("Schedule saved.");
      }
      await refreshZones();
    } catch (error) {
      console.error("Failed to save schedule", error);
      showScheduleError("Failed to save schedule.");
    }
  });
}

if (copyZonesBtn) {
  copyZonesBtn.addEventListener("click", async () => {
    if (isGlobalSchedule) {
      showScheduleError("Open a specific zone before copying to other zones.");
      return;
    }
    if (!activeScheduleZone) {
      showScheduleError("Open a zone schedule before copying.");
      return;
    }
    resetScheduleMessage();
    const targets = Array.from(copyZonesSelect ? copyZonesSelect.selectedOptions : [])
      .map((option) => option.value)
      .filter((value) => value && value !== activeScheduleZone);
    const uniqueTargets = Array.from(new Set(targets));
    if (!uniqueTargets.length) {
      showScheduleError("Select at least one zone to copy to.");
      return;
    }

    const entries = collectScheduleEntries();
    if (entries === null) {
      return;
    }
    const sortedEntries = sortScheduleEntries(entries);
    try {
      await fetchJson(`${API_BASE}/zones/${activeScheduleZone}/schedule`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entries: sortedEntries }),
      });
      await fetchJson(`${API_BASE}/zones/${activeScheduleZone}/schedule/clone`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_zones: uniqueTargets }),
      });
      renderScheduleEntries(sortedEntries, { markClean: true });
      showScheduleSuccess(`Copied schedule to ${uniqueTargets.length} zone(s).`);
      if (copyZonesSelect) {
        Array.from(copyZonesSelect.options).forEach((option) => {
          option.selected = false;
        });
      }
      await refreshZones();
    } catch (error) {
      console.error("Failed to copy schedule to zones", error);
      showScheduleError("Failed to copy schedule to selected zones.");
    }
  });
}

if (copyDayBtn) {
  copyDayBtn.addEventListener("click", () => {
    if (!copyDaySourceSelect || !copyDayTargetSelect) return;
    resetScheduleMessage();
    const sourceDay = Number.parseInt(copyDaySourceSelect.value, 10);
    const targets = Array.from(copyDayTargetSelect.selectedOptions)
      .map((option) => Number.parseInt(option.value, 10))
      .filter((value) => !Number.isNaN(value) && value !== sourceDay);
    const uniqueTargets = Array.from(new Set(targets));

    if (uniqueTargets.length === 0) {
      showScheduleError("Select at least one target day.");
      return;
    }

    const entries = collectScheduleEntries();
    if (entries === null) {
      return;
    }

    const sourceEntries = entries.filter((entry) => entry.day_of_week === sourceDay);
    if (!sourceEntries.length) {
      showScheduleError("Source day has no heating windows to copy.");
      return;
    }

    let updatedEntries = entries.filter((entry) => !uniqueTargets.includes(entry.day_of_week));
    uniqueTargets.forEach((targetDay) => {
      sourceEntries.forEach((entry) => {
        updatedEntries.push({
          day_of_week: targetDay,
          start_time: entry.start_time,
          end_time: entry.end_time,
          setpoint_f: entry.setpoint_f,
          enabled: entry.enabled,
        });
      });
    });

    updatedEntries = sortScheduleEntries(updatedEntries);
    renderScheduleEntries(updatedEntries);
    populateDaySelectors(sourceDay, uniqueTargets);
    showScheduleSuccess("Copied schedule to selected days. Remember to Save.");
  });
}

if (presetSelect) {
  presetSelect.addEventListener("change", () => {
    resetScheduleMessage();
  });
}

if (applyPresetBtn) {
  applyPresetBtn.addEventListener("click", async () => {
    if (!presetSelect || !presetSelect.value) {
      showScheduleError("Select a preset to apply.");
      return;
    }
    resetScheduleMessage();
    try {
      const preset = await fetchJson(`${API_BASE}/schedule/presets/${presetSelect.value}`);
      const entries = preset.entries || preset.Entries || [];
      renderScheduleEntries(entries, { markClean: false });
      showScheduleSuccess("Preset loaded. Remember to Save.");
    } catch (error) {
      console.error("Failed to load preset", error);
      showScheduleError("Failed to load preset.");
    }
  });
}

if (savePresetBtn) {
  savePresetBtn.addEventListener("click", async () => {
    const entries = collectScheduleEntries();
    if (entries === null) {
      return;
    }
    if (entries.length === 0) {
      showScheduleError("Add at least one window before saving as a preset.");
      return;
    }
    const name = window.prompt("Preset name:");
    if (!name) {
      return;
    }
    const description = window.prompt("Preset description (optional):", "");
    resetScheduleMessage();
    try {
      const sortedEntries = sortScheduleEntries(entries);
      const preset = await fetchJson(`${API_BASE}/schedule/presets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          description: description || null,
          entries: sortedEntries,
        }),
      });
      const presetId = preset.Id ?? preset.id;
      await refreshPresetOptions(presetId);
      showScheduleSuccess("Preset saved.");
    } catch (error) {
      console.error("Failed to save preset", error);
      showScheduleError("Failed to save preset.");
    }
  });
}

if (deletePresetBtn) {
  deletePresetBtn.addEventListener("click", async () => {
    if (!presetSelect || !presetSelect.value) {
      showScheduleError("Select a preset to delete.");
      return;
    }
    const id = Number.parseInt(presetSelect.value, 10);
    if (Number.isNaN(id)) {
      showScheduleError("Invalid preset selection.");
      return;
    }
    const preset = presetsCache.find((p) => (p.Id ?? p.id) === id);
    const name = preset ? preset.Name ?? preset.name ?? "this preset" : "this preset";
    const confirmed = window.confirm(`Delete preset "${name}"? This cannot be undone.`);
    if (!confirmed) {
      return;
    }
    resetScheduleMessage();
    try {
      const response = await fetch(`${API_BASE}/schedule/presets/${id}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || "Failed to delete preset");
      }
      await refreshPresetOptions();
      showScheduleSuccess("Preset deleted.");
    } catch (error) {
      console.error("Failed to delete preset", error);
      showScheduleError("Failed to delete preset.");
    }
  });
}

if (loadGlobalBtn) {
  loadGlobalBtn.addEventListener("click", async () => {
    resetScheduleMessage();
    try {
      const entries = await fetchJson(`${API_BASE}/schedule/default`);
      renderScheduleEntries(entries, { markClean: isGlobalSchedule });
      showScheduleSuccess(
        isGlobalSchedule
          ? "Reloaded global schedule."
          : "Loaded global schedule. Remember to Save."
      );
    } catch (error) {
      console.error("Failed to load global schedule", error);
      showScheduleError("Failed to load global schedule.");
    }
  });
}

if (clearScheduleBtn) {
  clearScheduleBtn.addEventListener("click", async () => {
    if (isGlobalSchedule || !activeScheduleZone) {
      return;
    }
    const confirmed = window.confirm(
      "Clear this zone's schedule and use the global default?"
    );
    if (!confirmed) {
      return;
    }
    resetScheduleMessage();
    try {
      await fetchJson(`${API_BASE}/zones/${activeScheduleZone}/schedule`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entries: [] }),
      });
      renderScheduleEntries([], { markClean: true });
      showScheduleSuccess("Zone will now use the global default schedule.");
      await refreshZones();
    } catch (error) {
      console.error("Failed to clear schedule", error);
      showScheduleError("Failed to clear schedule.");
    }
  });
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && scheduleModal && scheduleModal.classList.contains("open")) {
    attemptCloseScheduleModal();
  }
});

if (copyDaySourceSelect && copyDayTargetSelect) {
  copyDaySourceSelect.addEventListener("change", () => {
    const source = Number.parseInt(copyDaySourceSelect.value, 10);
    const selectedTargets = Array.from(copyDayTargetSelect.selectedOptions)
      .map((option) => Number.parseInt(option.value, 10))
      .filter((value) => !Number.isNaN(value) && value !== source);
    populateDaySelectors(source, selectedTargets);
  });
}

// Override Modal Functions
function showOverrideModal(zoneName, setpoint, onConfirm) {
  const modal = document.getElementById('overrideModal');
  const zoneNameEl = document.getElementById('overrideZoneName');
  const setpointEl = document.getElementById('overrideSetpoint');
  const timedOptions = document.getElementById('timedOptions');
  const untilInput = document.getElementById('overrideUntil');
  const confirmBtn = document.getElementById('overrideConfirm');
  const cancelBtn = document.getElementById('overrideCancel');
  const closeBtn = modal.querySelector('.modal-close');

  // Set default datetime to 2 hours from now
  const defaultUntil = new Date();
  defaultUntil.setHours(defaultUntil.getHours() + 2);
  untilInput.value = defaultUntil.toISOString().slice(0, 16);

  zoneNameEl.textContent = zoneName;
  setpointEl.textContent = setpoint.toFixed(1);
  modal.style.display = 'flex';

  // Handle timed mode radio selection
  const radios = modal.querySelectorAll('input[name="overrideMode"]');
  radios.forEach(radio => {
    radio.addEventListener('change', () => {
      timedOptions.style.display = radio.value === 'timed' ? 'block' : 'none';
    });
  });

  // Close handlers
  const closeModal = () => {
    modal.style.display = 'none';
    radios.forEach(radio => radio.removeEventListener('change', () => { }));
  };

  closeBtn.onclick = closeModal;
  cancelBtn.onclick = closeModal;
  modal.onclick = (e) => {
    if (e.target === modal) closeModal();
  };

  // Confirm handler
  confirmBtn.onclick = () => {
    const selectedMode = modal.querySelector('input[name="overrideMode"]:checked').value;
    const overrideData = {
      override_mode: selectedMode
    };

    if (selectedMode === 'timed') {
      const untilValue = untilInput.value;
      if (!untilValue) {
        alert('Please select a date and time for the override');
        return;
      }
      overrideData.override_until = new Date(untilValue).toISOString();
    }

    closeModal();
    onConfirm(overrideData);
  };
}

async function saveSetpoint(setpointBtn, row, zoneName, value, input, overrideData = null) {
  try {
    setpointBtn.disabled = true;
    setpointBtn.classList.add("loading");
    input.dataset.justSaved = 'true';

    const payload = { target_setpoint_f: value };
    if (overrideData) {
      payload.override_mode = overrideData.override_mode;
      if (overrideData.override_until) {
        payload.override_until = overrideData.override_until;
      }
    }

    console.log(`[Setpoint] Saving ${zoneName} setpoint: ${value}`, overrideData || '(no override)');
    const updated = await fetchJson(`${API_BASE}/zones/${zoneName}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    console.log(`[Setpoint] Response received:`, updated);

    // Track this override to prevent immediate refresh conflicts
    if (overrideData) {
      recentOverrides.set(zoneName, Date.now());
      console.log(`[Setpoint] Tracking recent override for ${zoneName} to prevent refresh conflicts`);
    }

    if (updated && updated.zone) {
      console.log(`[Setpoint] Updating cache with zone data, setpoint=${updated.zone.TargetSetpoint_F || updated.zone.target_setpoint_f}`);
      updateZonesCache({ zones: [updated.zone] });
    } else {
      console.log(`[Setpoint] Updating cache with direct data, setpoint=${updated.TargetSetpoint_F || updated.target_setpoint_f}`);
      updateZonesCache({ zones: [updated] });
    }

    setTimeout(() => {
      input.dataset.justSaved = 'false';
    }, 25000);
  } catch (error) {
    console.error("Failed to update setpoint", error);
    input.dataset.justSaved = 'false';
  } finally {
    setpointBtn.classList.remove("loading");
    setpointBtn.disabled = false;
  }
}

// Delegate button clicks so each row can trigger FORCE_ON/OFF/AUTO.
// Re-select zonesTable in case it wasn't available when module loaded
const zonesTableElement = zonesTable || document.querySelector("#zonesTable tbody");
if (zonesTableElement) {
  zonesTableElement.addEventListener("click", async (event) => {
    const setpointBtn = event.target.closest("button.setpoint-save");
    if (setpointBtn) {
      const row = setpointBtn.closest("tr[data-zone]");
      const zoneName = row.dataset.zone;
      const input = row.querySelector(".setpoint-input");
      const value = parseFloat(input.value);

      if (Number.isNaN(value)) {
        input.focus();
        input.classList.add("input-error");
        setTimeout(() => input.classList.remove("input-error"), 600);
        return;
      }

      // Check if zone is in AUTO mode - if so, show override modal
      const modeCell = row.querySelector(".mode");
      const currentMode = modeCell ? modeCell.textContent.trim() : "";

      console.log(`[Setpoint] Zone ${zoneName} mode check: UI shows '${currentMode}', saving value ${value}`);

      if (currentMode === "AUTO") {
        // Show override modal for zones currently in AUTO mode
        console.log(`[Setpoint] Showing override modal for AUTO zone ${zoneName}`);
        showOverrideModal(zoneName, value, async (overrideData) => {
          await saveSetpoint(setpointBtn, row, zoneName, value, input, overrideData);
        });
      } else {
        // For non-AUTO modes, save directly but let backend handle any mode conflicts
        console.log(`[Setpoint] Direct save for non-AUTO zone ${zoneName} (mode: ${currentMode})`);
        await saveSetpoint(setpointBtn, row, zoneName, value, input);
      }
      return;
    }

    const button = event.target.closest("button.action");
    if (!button) return;

    const row = button.closest("tr[data-zone]");
    const zoneName = row.dataset.zone;
    const command = button.dataset.action;

    try {
      button.disabled = true;
      button.classList.add("loading");
      console.log(`[Command] Sending ${command} to ${zoneName}`);
      const commandStartTime = performance.now();

      const response = await fetchJson(`${API_BASE}/zones/${zoneName}/command`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command }),
      });

      const responseTime = performance.now();
      console.log(`[Command] API response received in ${(responseTime - commandStartTime).toFixed(2)}ms`);
      console.log(`[Command] Full response from API:`, response);

      // Handle wrapped response - if response has a 'zone' property, use that
      let zoneData = response;
      if (response && response.zone && typeof response.zone === 'object') {
        zoneData = response.zone;
      }

      console.log(`[Command] Processed zone data:`, zoneData);
      console.log(`[Command] Has zone_name?`, !!zoneData?.zone_name);
      console.log(`[Command] Has ZoneName?`, !!zoneData?.ZoneName);

      // Immediately update UI with command response for instant feedback
      // Check for both lowercase zone_name and uppercase ZoneName
      if (zoneData && (zoneData.zone_name || zoneData.ZoneName)) {
        console.log(`[Command] IMMEDIATE UPDATE for ${zoneName}:`, zoneData);
        const updateStartTime = performance.now();
        updateZoneRow(row, zoneData);
        updateZonesCache({ zones: [zoneData] });
        const updateEndTime = performance.now();
        console.log(`[Command] UI update completed in ${(updateEndTime - updateStartTime).toFixed(2)}ms`);
      } else {
        // If command response is incomplete, fetch fresh data
        console.log(`[Command] FALLBACK - Incomplete response for ${zoneName}, fetching fresh data`);
        const fallbackStartTime = performance.now();
        try {
          const freshData = await fetchJson(`${API_BASE}/zones/${zoneName}`);
          if (freshData) {
            updateZoneRow(row, freshData);
            updateZonesCache({ zones: [freshData] });
            const fallbackEndTime = performance.now();
            console.log(`[Command] Fallback update completed in ${(fallbackEndTime - fallbackStartTime).toFixed(2)}ms`);
          }
        } catch (err) {
          console.error(`Failed to refresh zone ${zoneName} after command:`, err);
        }
      }
    } catch (error) {
      console.error("Failed to send command", error);
    } finally {
      button.classList.remove("loading");
      button.disabled = false;
    }
  });

  zonesTableElement.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target.classList.contains("setpoint-input")) {
      event.preventDefault();
      const row = event.target.closest("tr[data-zone]");
      const saveButton = row.querySelector(".setpoint-save");
      if (saveButton) {
        saveButton.click();
      }
    }
  });
}

// Manual refresh buttons simply call the async helpers.
if (refreshZonesBtn) {
  refreshZonesBtn.addEventListener("click", () => {
    refreshZones();
  });
}

if (statsRefreshBtn) {
  statsRefreshBtn.addEventListener("click", () => {
    refreshStats();
  });
}

if (statsWindowSelect) {
  statsWindowSelect.addEventListener("change", () => {
    refreshStats();
  });
}

if (statsDayInput) {
  statsDayInput.addEventListener("change", () => {
    refreshStats();
  });
}

if (statsDayInput && !statsDayInput.value) {
  statsDayInput.value = getTodayIso(DEFAULT_TIME_ZONE);
}

// Kick everything off as soon as the page loads.
const shouldPollZones = Boolean(zonesTable || outsideTempEl || systemUpdatedEl);
const shouldPollEvents = Boolean(eventsTableBody);
const shouldPollStats = Boolean(statsTableBody);
const shouldPollChart = Boolean(zoneSelect && chartCtx);
const currentPage = document.body?.dataset.page || "dashboard";

function initDashboardView() {
  hydrateDashboardFromCache();
  setPageLoading(false);
  if (shouldPollZones) {
    refreshZones();
  } else if (outsideTempEl || systemUpdatedEl) {
    refreshSystemStatus();
  }
  if (shouldPollEvents) {
    refreshEvents();
  }
  if (shouldPollStats) {
    refreshStats();
  }
  if (shouldPollChart) {
    initializeChart();
  }
}

function initGraphsView() {
  setPageLoading(false);
  initializeGraphsPage();
}

function initSchedulerView() {
  setPageLoading(false);
  initializeScheduler();
}

function initMetricsView() {
  setPageLoading(false);
  if (shouldPollStats) {
    refreshStats();
  }
  if (shouldPollEvents) {
    refreshEvents();
  }
  if (shouldPollChart) {
    initializeChart();
  }
}

const PAGE_INITIALIZERS = {
  dashboard: initDashboardView,
  graphs: initGraphsView,
  scheduler: initSchedulerView,
  metrics: initMetricsView,
};

(PAGE_INITIALIZERS[currentPage] || initDashboardView)();

if (zoneSelect) {
  zoneSelect.addEventListener("change", (event) => {
    loadZoneHistory(
      event.target.value,
      daySelect ? daySelect.value || undefined : undefined
    );
  });
}

// Lightweight auto-refresh so the dashboard stays current.
if (shouldPollZones || shouldPollEvents || shouldPollStats || shouldPollChart) {
  setInterval(() => {
    // Clean up old override tracking entries (older than 1 minute)
    const now = Date.now();
    for (const [zoneName, timestamp] of recentOverrides.entries()) {
      if (now - timestamp > 60000) {
        recentOverrides.delete(zoneName);
      }
    }

    if (shouldPollZones) {
      refreshZones();
    }
    if (shouldPollEvents) {
      refreshEvents();
    }
    if (shouldPollChart && zoneSelect) {
      loadZoneHistory(
        zoneSelect.value,
        daySelect ? daySelect.value || undefined : undefined
      );
    }
    if (shouldPollStats) {
      refreshStats();
    }
  }, 20000);
}

// --------- Chart Rendering ---------

function resizeCanvasToDisplaySize(canvas) {
  if (!canvas) return false;
  const ratio = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const logicalWidth = Math.max(rect.width, canvas.clientWidth || 0);
  const logicalHeight = Math.max(rect.height, canvas.clientHeight || 0);
  if (!logicalWidth || !logicalHeight) {
    return false;
  }
  const width = Math.round(logicalWidth * ratio);
  const height = Math.round(logicalHeight * ratio);
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
    return true;
  }
  return false;
}

async function loadZoneHistory(zone, options = undefined, context = null) {
  const canvas = context?.canvas ?? chartCanvas;
  const ctx = context?.ctx ?? chartCtx;
  if (!ctx || !canvas || !zone) return null;
  resizeCanvasToDisplaySize(canvas);
  const statusEl = context?.emptyEl ?? chartEmpty;
  if (statusEl) {
    statusEl.style.display = "flex";
    statusEl.textContent = "Loading…";
  }
  try {
    const request = buildHistoryRequest(options);
    const data = await fetchJson(
      `${API_BASE}/zones/${zone}/history?${request.queryString}`
    );
    const prepared = prepareHistoryData(data);
    const spanDays = Math.max(
      1,
      request.meta.day
        ? request.meta.resolvedSpanDays ?? 1
        : Math.round(request.meta.estimatedHours / 24)
    );
    const dayInfo = request.meta.day
      ? getDayWindow(request.meta.day, DEFAULT_TIME_ZONE, spanDays)
      : null;
    if (!prepared.hasSamples && !prepared.hasRuns) {
      if (statusEl) {
        statusEl.style.display = "flex";
        statusEl.textContent = "No data for selection.";
      }
      return {
        hasSamples: false,
        hasRuns: false,
      };
    }
    if (statusEl) {
      statusEl.style.display = "none";
    }
    renderZoneChart(
      prepared.samples,
      prepared.runEvents,
      zone,
      {
        dayInfo,
        timeZone: DEFAULT_TIME_ZONE,
        spanDays,
        rangeHours: request.meta.estimatedHours,
      },
      {
        canvas,
        ctx,
        emptyEl: statusEl,
      }
    );
    return {
      hasSamples: prepared.hasSamples,
      hasRuns: prepared.hasRuns,
    };
  } catch (error) {
    console.error("Failed to load zone history", error);
    if (statusEl) {
      statusEl.style.display = "flex";
      statusEl.textContent = "Failed to load data.";
    }
    return null;
  }
}

function renderZoneChart(samplePoints, runEvents, zoneName, options = {}, context = null) {
  const canvas = context?.canvas ?? chartCanvas;
  const ctx = context?.ctx ?? chartCtx;
  const statusEl = context?.emptyEl ?? chartEmpty;
  if (!ctx || !canvas) return;
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);

  const timeZone = options.timeZone || DEFAULT_TIME_ZONE;
  const dayInfo = options.dayInfo || null;
  const spanDayHint = Math.max(1, options.spanDays || 1);
  const rangeHoursHint = Math.max(1, options.rangeHours || spanDayHint * 24);

  const padding = {
    top: 60,
    right: 90,
    bottom: 60,
    left: 90,
  };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const HOUR_MS = 60 * 60 * 1000;
  const DAY_MS = 24 * HOUR_MS;
  const requestedSpanMs = rangeHoursHint * HOUR_MS;

  let spanMs = DAY_MS;
  let minAxis = 0;
  let maxAxis = 0;
  let sampleDataset;
  let runDataset;

  if (dayInfo) {
    const minUtc = dayInfo.startUtcMs;
    const maxUtc = dayInfo.endUtcMs;
    const startLocal = dayInfo.startLocalMs;
    spanMs = Math.max(maxUtc - minUtc, HOUR_MS);
    minAxis = 0;
    maxAxis = spanMs;
    sampleDataset = samplePoints
      .map((point) => {
        const utcMs = point.time.getTime();
        if (utcMs < minUtc || utcMs >= maxUtc) {
          return null;
        }
        const offset = getTimezoneOffsetMs(point.time, timeZone);
        const axisMs = utcMs + offset - startLocal;
        return { timeMs: axisMs, value: point.value };
      })
      .filter(
        (entry) =>
          entry &&
          Number.isFinite(entry.timeMs) &&
          !Number.isNaN(entry.value)
      )
      .sort((a, b) => a.timeMs - b.timeMs);
    runDataset = runEvents
      .map((entry) => {
        const utcMs = entry.time.getTime();
        if (utcMs < minUtc || utcMs >= maxUtc) {
          return null;
        }
        const offset = getTimezoneOffsetMs(entry.time, timeZone);
        const axisMs = utcMs + offset - startLocal;
        return { timeMs: axisMs, duration: entry.durationSeconds };
      })
      .filter(
        (entry) =>
          entry &&
          Number.isFinite(entry.timeMs) &&
          Number.isFinite(entry.duration)
      )
      .sort((a, b) => a.timeMs - b.timeMs);
  } else {
    const rawSamples = samplePoints
      .map((point) => ({
        timeMs: point.time.getTime(),
        value: point.value,
      }))
      .filter(
        (entry) =>
          Number.isFinite(entry.timeMs) && !Number.isNaN(entry.value)
      )
      .sort((a, b) => a.timeMs - b.timeMs);

    const latestTime = rawSamples.length
      ? rawSamples[rawSamples.length - 1].timeMs
      : Date.now();
    const minTimeUtc = latestTime - requestedSpanMs;

    sampleDataset = rawSamples
      .filter((entry) => entry.timeMs >= minTimeUtc)
      .slice(-2000);
    if (!sampleDataset.length && rawSamples.length) {
      sampleDataset = rawSamples.slice(-Math.min(rawSamples.length, 2000));
    }

    const desiredStart = minTimeUtc;
    const desiredEnd = minTimeUtc + requestedSpanMs;
    minAxis = desiredStart;
    maxAxis = desiredEnd;
    if (sampleDataset.length) {
      minAxis = Math.min(minAxis, sampleDataset[0].timeMs);
      maxAxis = Math.max(maxAxis, sampleDataset[sampleDataset.length - 1].timeMs);
    }

    runDataset = runEvents
      .map((entry) => ({
        timeMs: entry.time.getTime(),
        duration: entry.durationSeconds,
      }))
      .filter(
        (entry) => Number.isFinite(entry.timeMs) && Number.isFinite(entry.duration)
      )
      .filter((entry) => entry.timeMs >= desiredStart && entry.timeMs <= maxAxis)
      .sort((a, b) => a.timeMs - b.timeMs);
    spanMs = Math.max(maxAxis - minAxis, HOUR_MS);
  }

  if (!sampleDataset.length && !runDataset.length) {
    if (statusEl) {
      statusEl.style.display = "flex";
      statusEl.textContent = `No data for ${zoneName} in the selected window.`;
    }
    return;
  }

  if (statusEl) {
    statusEl.style.display = "none";
  }

  const temps = sampleDataset.map((entry) => entry.value);
  let minTemp = temps.length ? Math.min(...temps) : 60;
  let maxTemp = temps.length ? Math.max(...temps) : 80;
  if (temps.length) {
    const latestTemp = sampleDataset[sampleDataset.length - 1].value;
    minTemp = Math.min(minTemp, latestTemp, 50);
    maxTemp = Math.max(maxTemp, latestTemp);
  }
  if (minTemp === maxTemp) {
    minTemp -= 1;
    maxTemp += 1;
  }

  const axisRange = Math.max(maxAxis - minAxis, 1);
  const scaleX = (value) =>
    padding.left + ((value - minAxis) / axisRange) * innerWidth;
  const scaleTempY = (value) =>
    padding.top +
    innerHeight -
    ((value - minTemp) / (maxTemp - minTemp)) * innerHeight;

  const bucketCount = Math.min(
    Math.max(Math.round(spanMs / HOUR_MS), 24),
    24 * 31
  );
  const bucketSize = spanMs / bucketCount || HOUR_MS;
  const runBuckets = Array.from({ length: bucketCount }, () => ({
    sum: 0,
    count: 0,
  }));
  runDataset.forEach((entry) => {
    if (!Number.isFinite(entry.timeMs) || !Number.isFinite(entry.duration)) {
      return;
    }
    const clamped = Math.min(Math.max(entry.timeMs, minAxis), maxAxis);
    const relativeTime = clamped - minAxis;
    const index = Math.max(
      0,
      Math.min(bucketCount - 1, Math.floor(relativeTime / bucketSize))
    );
    runBuckets[index].sum += entry.duration;
    runBuckets[index].count += 1;
  });
  const runPoints = runBuckets.map((bucket, index) => {
    const baseTime = minAxis + bucketSize * (index + 0.5);
    if (!bucket.count) {
      return { timeMs: baseTime, value: null };
    }
    return {
      timeMs: baseTime,
      value: bucket.sum / 60,  // Total runtime in minutes for this time bucket
    };
  });
  const runValues = runPoints
    .filter((point) => point.value !== null && Number.isFinite(point.value))
    .map((point) => point.value);
  const hasRunData = runValues.length > 0;
  const runAxisMax = hasRunData ? Math.max(Math.max(...runValues), 1 / 60) : 1;
  const scaleRunY = (value) =>
    padding.top +
    innerHeight -
    (Math.max(value, 0) / runAxisMax) * innerHeight;

  ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padding.left, padding.top);
  ctx.lineTo(padding.left, height - padding.bottom + 10);
  ctx.lineTo(width - padding.right + 10, height - padding.bottom + 10);
  ctx.stroke();

  ctx.beginPath();
  ctx.moveTo(width - padding.right, padding.top);
  ctx.lineTo(width - padding.right, height - padding.bottom + 10);
  ctx.stroke();

  ctx.fillStyle = "rgba(255,255,255,0.55)";
  ctx.font = "16px sans-serif";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  const tempSteps = 4;
  for (let i = 0; i <= tempSteps; i += 1) {
    const t = minTemp + ((maxTemp - minTemp) / tempSteps) * i;
    const y = scaleTempY(t);
    ctx.fillText(`${t.toFixed(1)}°F`, padding.left - 12, y);
    ctx.strokeStyle = "rgba(255,255,255,0.05)";
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(width - padding.right, y);
    ctx.stroke();
  }

  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  const spanDays = spanMs / DAY_MS;
  let axisLabel = `Hour of Day (${timeZone})`;
  if (spanDays <= 1.5) {
    const totalHours = spanMs / HOUR_MS;
    const hourStep = Math.max(1, Math.round(totalHours / 24));
    const maxHour = Math.round(totalHours);
    for (let hour = 0; hour <= maxHour; hour += hourStep) {
      const tickRatio = totalHours ? hour / totalHours : 0;
      const tickTime = minAxis + spanMs * tickRatio;
      const x = scaleX(tickTime);
      if (hour === 0) {
        ctx.textAlign = "left";
      } else if (hour >= maxHour - hourStep / 2) {
        ctx.textAlign = "right";
      } else {
        ctx.textAlign = "center";
      }
      ctx.fillText(`${hour}h`, x, height - padding.bottom + 12);
      if (hour !== 0 && hour !== maxHour) {
        ctx.strokeStyle = "rgba(255,255,255,0.04)";
        ctx.beginPath();
        ctx.moveTo(x, padding.top);
        ctx.lineTo(x, height - padding.bottom);
        ctx.stroke();
      }
    }
  } else {
    axisLabel = `Day (${timeZone})`;
    const totalDays = Math.max(spanDayHint, Math.round(spanDays));
    const labelStep =
      totalDays > 14 ? Math.max(1, Math.round(totalDays / 14)) : 1;
    for (let dayIndex = 0; dayIndex < totalDays; dayIndex += 1) {
      const tickTime = minAxis + DAY_MS * (dayIndex + 0.5);
      const clampedTick = Math.min(Math.max(tickTime, minAxis), maxAxis);
      const x = scaleX(clampedTick);
      if (dayIndex % labelStep === 0) {
        const labelText = `${dayIndex + 1}`;
        ctx.textAlign = "center";
        ctx.fillText(labelText, x, height - padding.bottom + 12);
      }
      ctx.strokeStyle = "rgba(255,255,255,0.04)";
      ctx.beginPath();
      ctx.moveTo(x, padding.top);
      ctx.lineTo(x, height - padding.bottom);
      ctx.stroke();
    }
  }
  ctx.textAlign = "center";
  ctx.font = "16px sans-serif";
  ctx.fillStyle = "rgba(255,255,255,0.5)";
  ctx.fillText(
    axisLabel,
    padding.left + innerWidth / 2,
    height - padding.bottom + 32
  );
  ctx.fillStyle = "rgba(255,255,255,0.9)";
  ctx.font = "16px sans-serif";

  ctx.strokeStyle = "rgba(61, 165, 217, 0.85)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  sampleDataset.forEach((point, index) => {
    const clampedTime = Math.min(Math.max(point.timeMs, minAxis), maxAxis);
    const x = scaleX(clampedTime);
    const y = scaleTempY(point.value);
    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });
  ctx.stroke();

  if (hasRunData) {
    ctx.strokeStyle = "rgba(255, 196, 66, 0.95)";
    ctx.lineWidth = 2;
    let drawing = false;
    runPoints.forEach((point) => {
      const clampedTime = Math.min(Math.max(point.timeMs, minAxis), maxAxis);
      const x = scaleX(clampedTime);
      if (point.value === null) {
        if (drawing) {
          ctx.stroke();
        }
        drawing = false;
        return;
      }
      const y = scaleRunY(point.value);
      if (!drawing) {
        ctx.beginPath();
        ctx.moveTo(x, y);
        drawing = true;
      } else {
        ctx.lineTo(x, y);
      }
    });
    if (drawing) {
      ctx.stroke();
    }

    ctx.fillStyle = "rgba(255,255,255,0.6)";
    ctx.font = "16px sans-serif";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    const runSteps = 4;
    for (let i = 0; i <= runSteps; i += 1) {
      const value = (runAxisMax / runSteps) * i;
      const y = scaleRunY(value);
      ctx.fillText(`${value.toFixed(1)} min per hr`, width - padding.right + 62, y);
      ctx.strokeStyle = "rgba(255,196,66,0.13)";
      ctx.beginPath();
      ctx.moveTo(width - padding.right, y);
      ctx.lineTo(width - padding.right + 6, y);
      ctx.stroke();
    }
  }

  ctx.fillStyle = "rgba(255,255,255,0.95)";
  ctx.font = "16px sans-serif";
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  ctx.fillText(`${zoneName} Room Temp (°F)`, padding.left, padding.top - 28);
  if (hasRunData) {
    ctx.textAlign = "right";
    ctx.fillText(`Avg Run Time per Hour`, width - padding.right, padding.top - 28);
  }
}
function initializeChart() {
  if (!chartCtx || !zoneSelect) return;
  const choices = window.__ZONE_CHOICES__ || [];
  let initialZone = zoneSelect.value;
  if (!initialZone && choices.length) {
    const fallback = choices[0];
    initialZone = typeof fallback === "string" ? fallback : fallback?.zone;
    if (initialZone) {
      zoneSelect.value = initialZone;
    }
  }
  if (initialZone) {
    const selectedDay =
      daySelect && daySelect.value
        ? daySelect.value
        : daySelect
          ? getTodayIso(DEFAULT_TIME_ZONE)
          : undefined;
    if (daySelect && !daySelect.value && selectedDay) {
      daySelect.value = selectedDay;
    }
    loadZoneHistory(initialZone, selectedDay);
  } else {
    // No zone selected - ensure chart shows default message
    if (chartEmpty) {
      chartEmpty.style.display = "flex";
      chartEmpty.textContent = "Select a zone to view its history.";
    }
  }
}

function resolveGraphsDayValue(dayOverride) {
  if (dayOverride === null) return null;
  if (dayOverride === undefined) {
    return graphsDayInput?.value || null;
  }
  return dayOverride;
}

function getCurrentMonthValue() {
  const now = new Date();
  return String(now.getMonth() + 1).padStart(2, "0");
}

function ensureGraphsMonthSelection() {
  if (!graphsMonthSelect) return null;
  if (!graphsMonthSelect.value) {
    graphsMonthSelect.value = getCurrentMonthValue();
  }
  return graphsMonthSelect.value;
}

function getDaysInMonth(year, monthNumber) {
  return new Date(year, monthNumber, 0).getDate();
}

function getMonthSelectionInfo() {
  const value = ensureGraphsMonthSelection();
  if (!value) return null;
  const monthNumber = Number.parseInt(value, 10);
  if (Number.isNaN(monthNumber)) return null;
  const now = new Date();
  const year = now.getFullYear();
  const days = getDaysInMonth(year, monthNumber);
  const monthName = MONTH_LABELS[monthNumber - 1] || `Month ${monthNumber}`;
  const isoDay = `${year}-${value.padStart(2, "0")}-01`;
  return {
    isoDay,
    monthName,
    year,
    spanDays: days,
  };
}

function formatDisplayDate(isoValue) {
  if (!isoValue) return isoValue;
  const parsed = parseUtcTimestamp(`${isoValue}T00:00:00Z`);
  if (!parsed) return isoValue;
  return parsed.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function getGraphsRangeSelection(dayOverride) {
  const range = graphsRangeSelect?.value || "day";
  const normalizedDay = resolveGraphsDayValue(dayOverride);
  const buildRolling = (hours, label) => ({
    range,
    label,
    params: { hours },
  });
  if (range === "week") {
    if (normalizedDay) {
      const startDate = parseUtcTimestamp(`${normalizedDay}T00:00:00Z`);
      let dayBeforeNormalized = normalizedDay;
      if (startDate) {
        const adjusted = new Date(
          Date.UTC(
            startDate.getUTCFullYear(),
            startDate.getUTCMonth(),
            startDate.getUTCDate() - 1
          )
        );
        dayBeforeNormalized = adjusted.toISOString().slice(0, 10);
      }
      return {
        range,
        label: `Showing week starting ${formatDisplayDate(dayBeforeNormalized)}`,
        params: { day: dayBeforeNormalized, spanDays: 7 },
      };
    }
    return buildRolling(24 * 7, "Showing last 7 days (rolling).");
  }
  if (range === "month") {
    const monthInfo = getMonthSelectionInfo();
    if (monthInfo) {
      return {
        range,
        label: `Showing ${monthInfo.monthName} ${monthInfo.year}`,
        params: { day: monthInfo.isoDay, spanDays: monthInfo.spanDays },
      };
    }
    return buildRolling(24 * 30, "Showing current month (rolling).");
  }
  if (normalizedDay) {
    return {
      range,
      label: `Showing data for ${formatDisplayDate(normalizedDay)}`,
      params: { day: normalizedDay, spanDays: 1 },
    };
  }
  return buildRolling(24, "Showing last 24 hours (rolling).");
}

function buildHistoryRequest(options = undefined) {
  let day;
  let hours;
  let spanDays;
  if (options && typeof options === "object" && !Array.isArray(options)) {
    day = options.day;
    hours = options.hours;
    spanDays = options.spanDays;
  } else if (typeof options === "string") {
    day = options;
  } else if (options) {
    day = options;
  }
  const normalizedHours =
    typeof hours === "number" && Number.isFinite(hours)
      ? Math.max(1, Math.floor(hours))
      : null;
  const normalizedSpanDays =
    typeof spanDays === "number" && Number.isFinite(spanDays)
      ? Math.max(1, Math.min(31, Math.floor(spanDays)))
      : null;
  const resolvedSpanDays = day ? normalizedSpanDays ?? 1 : null;
  let estimatedHours = normalizedHours ?? 24;
  if (day) {
    estimatedHours = (resolvedSpanDays ?? 1) * 24;
  } else if (!normalizedHours) {
    estimatedHours = 24;
  }
  let limitValue = 4000;
  if (estimatedHours > 24 && estimatedHours < 168) {
    limitValue = 6000;
  } else if (estimatedHours >= 168 && estimatedHours < 720) {
    limitValue = 8000;
  } else if (estimatedHours >= 720) {
    limitValue = 12000;
  }
  const params = new URLSearchParams({
    limit: String(limitValue),
    tz: DEFAULT_TIME_ZONE,
  });
  if (day) {
    params.set("day", day);
    if (resolvedSpanDays && resolvedSpanDays > 1) {
      params.set("span_days", String(resolvedSpanDays));
    }
  } else {
    const hoursParam = normalizedHours ?? 24;
    params.set("hours", String(hoursParam));
  }
  const estimatedSpanDays = day
    ? resolvedSpanDays ?? 1
    : Math.max(1, estimatedHours / 24);
  const maxSamplesTarget = Math.max(
    800,
    Math.min(4000, Math.round(estimatedSpanDays * 250))
  );
  params.set("max_samples", String(maxSamplesTarget));
  return {
    queryString: params.toString(),
    meta: {
      day: day || null,
      resolvedSpanDays,
      estimatedHours,
    },
  };
}

function getCachedHistories(cacheKey) {
  const entry = graphsCache.get(cacheKey);
  if (!entry) return null;
  if (entry.expiresAt < Date.now()) {
    graphsCache.delete(cacheKey);
    return null;
  }
  return entry.data;
}

function setCachedHistories(cacheKey, data) {
  graphsCache.set(cacheKey, {
    data,
    expiresAt: Date.now() + GRAPHS_CACHE_TTL,
  });
}

function readDashboardCache(key) {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    if (parsed.expiresAt && parsed.expiresAt < Date.now()) {
      window.localStorage.removeItem(key);
      if (DASHBOARD_CACHE_DEBUG) {
        console.info(`[cache] ${key} expired`);
      }
      return null;
    }
    if (DASHBOARD_CACHE_DEBUG) {
      console.info(`[cache] hit ${key}`);
    }
    return parsed.data ?? null;
  } catch (error) {
    return null;
  }
}

function writeDashboardCache(key, value) {
  try {
    window.localStorage.setItem(
      key,
      JSON.stringify({
        data: value,
        expiresAt: Date.now() + DASHBOARD_CACHE_TTL,
      })
    );
    if (DASHBOARD_CACHE_DEBUG) {
      console.info(`[cache] write ${key}`);
    }
  } catch (error) {
    // best effort cache
  }
}

function updateZonesCache(partial) {
  const existing = readDashboardCache(DASHBOARD_ZONES_CACHE_KEY) || {};
  writeDashboardCache(DASHBOARD_ZONES_CACHE_KEY, {
    ...existing,
    ...partial,
  });
}

function renderZones(zones) {
  if (!zonesTable || !Array.isArray(zones)) return;
  zones.forEach((zone) => {
    const zoneName = getProp(zone, "zone_name", "ZoneName", "zoneName");
    const row = zoneName ? zonesTable.querySelector(`tr[data-zone="${zoneName}"]`) : null;
    if (row) {
      updateZoneRow(row, zone);
    }
  });
}

function renderSystemStatusData(system) {
  if (!system) return;
  if (outsideTempEl) {
    const temp = system.outside_temp_f ?? system.OutsideTemp_F ?? null;
    outsideTempEl.textContent =
      temp === null || temp === undefined ? "—" : `${Number.parseFloat(temp).toFixed(1)} °F`;
  }
  if (systemUpdatedEl) {
    systemUpdatedEl.textContent = system.updated_at ?? system.UpdatedAt ?? "—";
  }
}

function renderEvents(events) {
  if (!eventsTableBody || !Array.isArray(events)) return;
  eventsTableBody.innerHTML = "";
  events.forEach((event) => {
    const timestamp = event.timestamp ?? event.Timestamp ?? "";
    const [fallbackEventDate, fallbackEventTime] = splitTimestamp(timestamp);
    const eventDate = event.event_date ?? event.EventDate ?? event.eventDate ?? fallbackEventDate;
    const eventTime = event.event_time ?? event.EventTime ?? event.eventTime ?? fallbackEventTime;
    const source = event.source ?? event.Source ?? "—";
    const room = event.room_name ?? event.RoomName ?? "—";
    const state = event.event ?? event.Event ?? "—";
    const zoneTemp = event.zone_room_temp_f ?? event.ZoneRoomTemp_F ?? undefined;
    const pipeTemp = event.pipe_temp_f ?? event.PipeTemp_F ?? undefined;
    const outsideTemp = event.outside_temp_f ?? event.OutsideTemp_F ?? undefined;
    const duration = event.duration_seconds ?? event.DurationSeconds ?? undefined;

    const tr = document.createElement("tr");
    tr.append(createCell(source));
    tr.append(createCell(room));
    tr.append(createCell(state));
    tr.append(createCell(formatDuration(duration)));
    tr.append(createCell(formatTemp(zoneTemp)));
    tr.append(createCell(formatTemp(pipeTemp)));
    tr.append(createCell(formatTemp(outsideTemp)));
    tr.append(createCell(eventDate));
    tr.append(createCell(formatTime(eventTime)));
    eventsTableBody.appendChild(tr);
  });
}

function renderStats(stats, metadata = {}) {
  if (!statsTableBody || !Array.isArray(stats)) return;
  statsTableBody.innerHTML = "";
  const windowValue = metadata.windowValue ?? (statsWindowSelect ? statsWindowSelect.value : "day");
  const dayValue = metadata.dayValue ?? (statsDayInput?.value || null);
  const labels = { day: "Day", week: "Week", month: "Month" };
  const windowLabel = labels[windowValue] ?? windowValue;
  if (statsCallsHeader) {
    statsCallsHeader.textContent = `Calls (${windowLabel})`;
  }
  if (statsTotalHeader) {
    statsTotalHeader.textContent = `Total Run (${windowLabel})`;
  }
  stats.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.zone_name}</td>
      <td>${row.room_name ?? "—"}</td>
      <td>${getProp(row, "calls_in_window", "CallsInWindow") ?? 0}</td>
      <td>${formatDuration(getProp(row, "average_run_seconds_per_call", "AverageRunSecondsPerCall"))}</td>
      <td>${formatDuration(getProp(row, "total_run_window_seconds", "TotalRunWindowSeconds"))}</td>
      <td>${formatTemp(getProp(row, "average_room_temp_f", "AverageRoomTemp_F"))}</td>
    `;
    statsTableBody.appendChild(tr);
  });
  if (statsSummaryLabel) {
    if (stats.length) {
      const first = stats[0];
      const startTs = parseUtcTimestamp(getProp(first, "window_start", "WindowStart"));
      const endTs = parseUtcTimestamp(getProp(first, "window_end", "WindowEnd"));
      const formatter = new Intl.DateTimeFormat("en-US", {
        timeZone: DEFAULT_TIME_ZONE,
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
      const startLabel = startTs ? formatter.format(startTs) : null;
      const endLabel = endTs ? formatter.format(endTs) : null;
      if (startLabel && endLabel) {
        statsSummaryLabel.textContent = `${windowLabel} summary (${startLabel} → ${endLabel})`;
      } else if (dayValue) {
        statsSummaryLabel.textContent = `${windowLabel} summary for ${dayValue}`;
      } else {
        statsSummaryLabel.textContent = `${windowLabel} summary (rolling)`;
      }
    } else if (dayValue) {
      statsSummaryLabel.textContent = `${windowLabel} summary for ${dayValue}`;
    } else {
      statsSummaryLabel.textContent = `${windowLabel} summary (rolling)`;
    }
  }
}

function hydrateDashboardFromCache() {
  const zonesCache = readDashboardCache(DASHBOARD_ZONES_CACHE_KEY);
  if (zonesCache) {
    if (DASHBOARD_CACHE_DEBUG) {
      console.info("[dashboard] hydrating zones cache", {
        zones: zonesCache.zones ? zonesCache.zones.length : 0,
        hasSystem: Boolean(zonesCache.system),
      });
    }
    if (zonesCache.zones) {
      renderZones(zonesCache.zones);
    }
    if (zonesCache.system) {
      renderSystemStatusData(zonesCache.system);
    }
  }
  const eventsCache = readDashboardCache(DASHBOARD_EVENTS_CACHE_KEY);
  if (eventsCache?.events) {
    if (DASHBOARD_CACHE_DEBUG) {
      console.info("[dashboard] hydrating events cache", { count: eventsCache.events.length });
    }
    renderEvents(eventsCache.events);
  }
  const statsCache = readDashboardCache(DASHBOARD_STATS_CACHE_KEY);
  if (
    statsCache?.stats &&
    (!statsCache.windowValue || statsCache.windowValue === (statsWindowSelect?.value || "day")) &&
    (!statsCache.dayValue || statsCache.dayValue === (statsDayInput?.value || ""))
  ) {
    if (DASHBOARD_CACHE_DEBUG) {
      console.info("[dashboard] hydrating stats cache", {
        rows: statsCache.stats.length,
        windowValue: statsCache.windowValue,
        dayValue: statsCache.dayValue,
      });
    }
    renderStats(statsCache.stats, {
      windowValue: statsCache.windowValue,
      dayValue: statsCache.dayValue,
    });
  }
}

function prepareHistoryData(data) {
  const samples = data
    .map((event) => {
      const timestamp =
        event.timestamp ?? event.Timestamp ?? event.updated_at ?? null;
      const temp = event.zone_room_temp_f ?? event.ZoneRoomTemp_F;
      const parsed = parseUtcTimestamp(timestamp);
      if (!parsed || temp === null || temp === undefined) {
        return null;
      }
      return {
        time: parsed,
        value: Number.parseFloat(temp),
      };
    })
    .filter((point) => point && !Number.isNaN(point.value))
    .sort((a, b) => a.time - b.time);

  const timeline = data
    .map((event) => {
      const timestamp =
        event.timestamp ?? event.Timestamp ?? event.updated_at ?? null;
      const eventName = String(event.event ?? event.Event ?? "").toUpperCase();
      const parsed = parseUtcTimestamp(timestamp);
      if (!parsed || !eventName) {
        return null;
      }
      const duration = event.duration_seconds ?? event.DurationSeconds ?? null;
      const durationValue =
        duration === null || duration === undefined
          ? null
          : Number.parseFloat(duration);
      return {
        time: parsed,
        type: eventName,
        durationSeconds:
          durationValue !== null && Number.isFinite(durationValue)
            ? durationValue
            : null,
      };
    })
    .filter(Boolean)
    .sort((a, b) => a.time - b.time);

  const runEvents = [];
  let pendingOn = null;
  timeline.forEach((entry) => {
    if (entry.type === "ON") {
      pendingOn = entry.time;
      return;
    }
    if (entry.type !== "OFF") {
      return;
    }
    let duration = entry.durationSeconds;
    if ((duration === null || duration === undefined) && pendingOn) {
      const diffSeconds = (entry.time.getTime() - pendingOn.getTime()) / 1000;
      if (Number.isFinite(diffSeconds) && diffSeconds >= 0) {
        duration = diffSeconds;
      }
    }
    if (duration !== null && duration !== undefined && duration >= 0) {
      runEvents.push({
        time: entry.time,
        durationSeconds: duration,
      });
    }
    pendingOn = null;
  });

  return {
    samples,
    runEvents,
    hasSamples: samples.length > 0,
    hasRuns: runEvents.length > 0,
  };
}

async function loadGraphsForDay(dayOverride, { force = false } = {}) {
  console.log("[Graphs] loadGraphsForDay called, cards.length:", graphsState.cards.length);
  if (!graphsState.cards.length) {
    console.log("[Graphs] No cards found, returning early");
    return;
  }
  const selection = getGraphsRangeSelection(dayOverride);
  const request = buildHistoryRequest(selection.params);
  const zones = graphsState.cards.map((entry) => entry.zone);
  console.log("[Graphs] Loading history for zones:", zones);
  const cacheKey = `${request.queryString}|${zones.join(",")}`;
  if (graphsInfo) {
    graphsInfo.textContent = selection.label;
  }
  if (!zones.length) return;
  graphsState.lastMeta = null;
  graphsState.cards.forEach((entry) => {
    if (entry.emptyEl) {
      entry.emptyEl.style.display = "flex";
      entry.emptyEl.textContent = "Loading…";
    }
    if (entry.statusEl) {
      entry.statusEl.textContent = "Loading…";
    }
    entry.lastPayload = null;
  });
  try {
    let histories = force ? null : getCachedHistories(cacheKey);
    if (!histories) {
      console.log("[Graphs] Fetching history from API:", `${API_BASE}/zones/history/batch?${request.queryString}`);
      const response = await fetchJson(
        `${API_BASE}/zones/history/batch?${request.queryString}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ zones }),
        }
      );
      console.log("[Graphs] API response:", response);
      histories = response?.histories || {};
      setCachedHistories(cacheKey, histories);
    } else {
      console.log("[Graphs] Using cached histories");
    }
    const spanDays = Math.max(
      1,
      request.meta.day
        ? request.meta.resolvedSpanDays ?? 1
        : Math.round(request.meta.estimatedHours / 24)
    );
    const dayInfo = request.meta.day
      ? getDayWindow(request.meta.day, DEFAULT_TIME_ZONE, spanDays)
      : null;
    const chartMeta = {
      dayInfo,
      timeZone: DEFAULT_TIME_ZONE,
      spanDays,
      rangeHours: request.meta.estimatedHours,
    };
    graphsState.lastMeta = chartMeta;
    const nowLabel = new Date().toLocaleTimeString();
    zones.forEach((zone) => {
      const entry = graphsState.cardMap.get(zone);
      if (!entry) return;
      const rawHistory = histories[zone] || [];
      const prepared = prepareHistoryData(rawHistory);
      if (!prepared.hasSamples && !prepared.hasRuns) {
        entry.lastPayload = null;
        if (entry.emptyEl) {
          entry.emptyEl.style.display = "flex";
          entry.emptyEl.textContent = "No data for selection.";
        }
        if (entry.statusEl) {
          entry.statusEl.textContent = `No data · ${nowLabel}`;
        }
        return;
      }
      entry.lastPayload = prepared;
      if (entry.emptyEl) {
        entry.emptyEl.style.display = "none";
      }
      renderZoneChart(
        prepared.samples,
        prepared.runEvents,
        entry.zone,
        chartMeta,
        {
          canvas: entry.canvas,
          ctx: entry.ctx,
          emptyEl: entry.emptyEl,
        }
      );
      if (entry.statusEl) {
        entry.statusEl.textContent = `Updated · ${nowLabel}`;
      }
    });
  } catch (error) {
    console.error("Failed to load graphs", error);
    graphsState.cards.forEach((entry) => {
      if (entry.emptyEl) {
        entry.emptyEl.style.display = "flex";
        entry.emptyEl.textContent = "Failed to load data.";
      }
      if (entry.statusEl) {
        entry.statusEl.textContent = "Error";
      }
    });
  }
}

function redrawGraphs() {
  if (!graphsState.cards.length || !graphsState.lastMeta) return;
  graphsState.cards.forEach((entry) => {
    if (!entry.lastPayload) return;
    resizeCanvasToDisplaySize(entry.canvas);
    renderZoneChart(
      entry.lastPayload.samples,
      entry.lastPayload.runEvents,
      entry.zone,
      graphsState.lastMeta,
      {
        canvas: entry.canvas,
        ctx: entry.ctx,
        emptyEl: entry.emptyEl,
      }
    );
  });
}

function initializeGraphsPage() {
  if (!graphsGrid) return;
  graphsState.cards = Array.from(graphsGrid.querySelectorAll(".zone-graph-card"))
    .map((card) => {
      const zone = card.dataset.zone;
      const canvas = card.querySelector("canvas");
      if (!zone || !canvas) return null;
      resizeCanvasToDisplaySize(canvas);
      return {
        card,
        zone,
        canvas,
        ctx: canvas.getContext("2d"),
        emptyEl: card.querySelector(".graph-empty"),
        statusEl: card.querySelector('[data-role="status"]'),
        lastPayload: null,
      };
    })
    .filter(Boolean);

  if (!graphsState.cards.length) return;
  graphsState.cardMap = new Map();
  graphsState.cards.forEach((entry) => {
    graphsState.cardMap.set(entry.zone, entry);
  });

  const updateInputMode = () => {
    const isMonth = graphsRangeSelect?.value === "month";
    if (graphsDayWrapper) {
      graphsDayWrapper.classList.toggle("hidden", Boolean(isMonth));
    }
    if (graphsMonthWrapper) {
      graphsMonthWrapper.classList.toggle("hidden", !isMonth);
    }
    if (isMonth) {
      ensureGraphsMonthSelection();
    }
  };

  const reload = (dayOverride) => {
    graphsState.cards.forEach((entry) => {
      resizeCanvasToDisplaySize(entry.canvas);
    });
    loadGraphsForDay(dayOverride);
  };

  if (graphsRefreshBtn) {
    graphsRefreshBtn.addEventListener("click", () => {
      graphsCache.clear();
      loadGraphsForDay(undefined, { force: true });
    });
  }

  if (graphsClearBtn) {
    graphsClearBtn.addEventListener("click", () => {
      if (graphsDayInput) {
        graphsDayInput.value = "";
      }
      if (graphsRangeSelect) {
        graphsRangeSelect.value = "day";
      }
      if (graphsMonthSelect) {
        graphsMonthSelect.value = getCurrentMonthValue();
      }
      updateInputMode();
      graphsCache.clear();
      loadGraphsForDay(null, { force: true });
    });
  }

  if (graphsDayInput) {
    graphsDayInput.addEventListener("change", () => {
      reload();
    });
  }

  if (graphsRangeSelect) {
    graphsRangeSelect.addEventListener("change", () => {
      updateInputMode();
      reload();
    });
  }

  if (graphsMonthSelect) {
    graphsMonthSelect.addEventListener("change", () => {
      if (graphsRangeSelect?.value === "month") {
        reload();
      }
    });
  }

  updateInputMode();
  loadGraphsForDay();

  window.addEventListener("resize", () => {
    if (graphsState.resizeTimer) {
      clearTimeout(graphsState.resizeTimer);
    }
    graphsState.resizeTimer = window.setTimeout(() => {
      redrawGraphs();
    }, 250);
  });
}
async function applyPresetToZone(zone, presetId) {
  if (!zone || !presetId) return;
  try {
    const preset = await fetchJson(`${API_BASE}/schedule/presets/${presetId}`);
    const normalized = normalizeScheduleEntries(preset.entries ?? preset.Entries ?? []);
    const state = ensureZoneState(zone);
    state.entries = normalized;
    state.dirty = true;
    state.usingGlobal = false;
    renderSchedulerBubbles(zone);
    updateSchedulerControls();
  } catch (error) {
    console.error("Failed to load preset", error);
    window.alert("Failed to apply preset.");
  }
}

async function saveCurrentZoneAsPreset(zone) {
  if (!zone) return;
  const state = schedulerState[zone];
  if (!state || !state.entries.length) {
    window.alert("Add at least one setpoint before saving as a preset.");
    return;
  }
  const name = window.prompt("Preset name:");
  if (!name) return;
  const description = window.prompt("Preset description (optional):", "") || null;
  const payload = {
    name,
    description,
    entries: serializeSchedulerEntries(state.entries),
  };
  console.log("[Scheduler] Saving preset with payload:", JSON.stringify(payload, null, 2));
  try {
    const preset = await fetchJson(`${API_BASE}/schedule/presets`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    console.log("[Scheduler] Preset saved successfully:", preset);
    const presetId = preset.Id ?? preset.id;
    await loadSchedulerPresets(presetId);
    window.alert("Preset saved.");
  } catch (error) {
    console.error("Failed to save preset - Error details:", error);
    const errorMsg = error.message || error.detail || JSON.stringify(error);
    window.alert(`Failed to save preset: ${errorMsg}`);
  }
}
