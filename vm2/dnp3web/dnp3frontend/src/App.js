import { useState, useEffect, useRef } from "react";

const API_BASE = "http://localhost:5000";

export default function App() {
  const [ip, setIp]               = useState("");
  const [ip2, setIp2]             = useState("");
  const [inputIp, setInputIp]     = useState("");
  const [inputIp2, setInputIp2]   = useState("");
  const [connected, setConnected] = useState(false);
  const [tags, setTags]           = useState(null);
  const [error, setError]         = useState("");
  const [connecting, setConnecting] = useState(false);
  const [controlMsg, setControlMsg] = useState("");
  const [polling, setPolling]     = useState(false);
  const [pollDuration, setPollDuration] = useState("");
  const [pollRemaining, setPollRemaining] = useState(0);
  const [lastUpdated, setLastUpdated] = useState(null);
  const pollRef = useRef(null);
  const tagRef  = useRef(null);

  useEffect(() => {
    if (connected && ip) {
      fetchTags();
      tagRef.current = setInterval(fetchTags, 1000);
    }
    return () => clearInterval(tagRef.current);
  }, [connected, ip]);

  const fetchTags = async () => {
    try {
      const res  = await fetch(`${API_BASE}/api/tags?ip=${ip}&ip2=${ip2}`);
      const data = await res.json();
      if (data.error) {
        setError(data.error);
      } else {
        setTags(data);
        setLastUpdated(new Date().toLocaleTimeString());
        setError("");
      }
    } catch {
      setError("Connection to API lost — is the Docker container running?");
    }
  };

  const handleConnect = async () => {
    if (!inputIp || !inputIp2) return;
    setConnecting(true);
    setError("");
    try {
      const res  = await fetch(`${API_BASE}/api/connect`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ ip: inputIp }),
      });
      const data = await res.json();
      if (data.success) {
        setIp(inputIp);
        setIp2(inputIp2);
        setConnected(true);
      } else {
        setError(data.error || "Could not connect to OpenPLC");
      }
    } catch {
      setError("Could not reach API server — run: docker start dnp3web");
    }
    setConnecting(false);
  };

  const handleDisconnect = () => {
    clearInterval(tagRef.current);
    clearInterval(pollRef.current);
    setConnected(false);
    setIp("");
    setIp2("");
    setTags(null);
    setError("");
    setControlMsg("");
    setPolling(false);
  };

  const handleControl = async (action) => {
    setControlMsg("");
    try {
      const res = await fetch(`${API_BASE}/api/control`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ip, ip2, action }),
      });
      const data = await res.json();
      if (data.success) {
        setControlMsg(`Switch set ${action.toUpperCase()} successfully${data.note ? ` (${data.note})` : ''}`);
        setTimeout(fetchTags, 1000);
        setTimeout(() => setControlMsg(""), 4000);
      } else {
        setControlMsg(`Error: ${data.error}`);
      }
    } catch {
      setControlMsg("Control command failed");
    }
  };

  const handlePoll = () => {
    const duration = parseInt(pollDuration);
    if (!duration || duration < 1) return;
    setPolling(true);
    setPollRemaining(duration);
    fetchTags();

    let remaining = duration;
    pollRef.current = setInterval(() => {
      remaining -= 2;
      setPollRemaining(Math.max(remaining, 0));
      fetchTags();
      if (remaining <= 0) {
        clearInterval(pollRef.current);
        setPolling(false);
        setPollRemaining(0);
      }
    }, 2000);
  };

  const stopPoll = () => {
    clearInterval(pollRef.current);
    setPolling(false);
    setPollRemaining(0);
  };

  // ── IP entry screen ────────────────────────────────────────────────────────
  if (!connected) {
    return (
      <div style={s.page}>
        <div style={s.loginCard}>
          <div style={s.loginTitle}>DNP3 SCADA MASTER</div>
          <div style={s.loginSub}>OT/ICS Lab Environment</div>
          <div style={s.divider} />
          <div style={s.fieldLabel}>PLC 1 IP Address</div>
          <input
            style={s.input}
            placeholder="e.g. 10.80.128.205"
            value={inputIp}
            onChange={e => setInputIp(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleConnect()}
            autoFocus
          />
          <div style={s.fieldLabel}>PLC 2 (Backup) IP Address</div>
          <input
            style={s.input}
            placeholder="e.g. 10.80.128.205"
            value={inputIp2}
            onChange={e => setInputIp2(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleConnect()}
          />
          {error && <div style={s.errorBox}>{error}</div>}
          <button
            style={{ ...s.btnPrimary, opacity: connecting ? 0.7 : 1 }}
            onClick={handleConnect}
            disabled={connecting}
          >
            {connecting ? "Connecting…" : "Connect"}
          </button>
          <div style={s.hint}>IP resets when you leave or refresh the page</div>
        </div>
      </div>
    );
  }

  const backupActive = tags?.backup_active === "ON";

  // colorRule determines how the Value cell is colored:
  //   "status"       — ON/CLOSED = muted green, OFF/OPEN = neutral gray
  //   "alarm"        — ON = red (bad), OFF = green (good) — inverted vs "status"
  //   "backupAlarm"  — ON = amber (attention: failover active), OFF = neutral gray
  //   "numeric"      — always navy, no state meaning
  const rows = [
    { name: "Gauge",             label: "Gauge",                    key: "gauge",            source: "DNP3 Analog idx1", colorRule: "numeric" },
    { name: "Substation_Pipe",   label: "Substation Pipe",          key: "pipe",             source: "DNP3 Binary idx0", colorRule: "status" },
    { name: "Substation_Switch", label: "Substation Switch",        key: "switch",           source: "DNP3 BOS idx0",    colorRule: "status" },
    { name: "Backup_Active",     label: "Backup Active",            key: "backup_active",    source: "Modbus coil1",     colorRule: "backupAlarm" },
    { name: "T1_Temp_Alarm",     label: "T1 Temp Alarm",             key: "t1_temp_alarm",    source: "DNP3 Binary idx1", colorRule: "alarm" },
    { name: "Bus1_Voltage_kV",   label: "Bus 1 Voltage (kV)",        key: "bus1_voltage",     source: "DNP3 Analog idx2", colorRule: "numeric" },
    { name: "FeederCurrent_A",   label: "Feeder Current (A)",        key: "feeder_current",   source: "DNP3 Analog idx3", colorRule: "numeric" },
    { name: "T1_WindingTemp_C",  label: "T1 Winding Temp (°C)",      key: "t1_winding_temp",  source: "DNP3 Analog idx4", colorRule: "numeric" },
    { name: "Breaker_OpCount",   label: "Breaker Op Count",          key: "breaker_opcount",  source: "DNP3 Analog idx5", colorRule: "numeric" },
  ];

  // ── Dashboard ──────────────────────────────────────────────────────────────
  return (
    <div style={s.page}>
      <div style={s.frame}>
        <div style={s.header}>
          <div style={s.headerTitle}>
            DNP3 SCADA MASTER — connected to {backupActive ? ip2 : ip}
          </div>
          <div style={s.headerRight}>
            {lastUpdated && `last poll ${lastUpdated}`}
            {" · "}
            <span style={s.disconnectLink} onClick={handleDisconnect}>disconnect</span>
          </div>
        </div>

        {backupActive && (
          <div style={s.alarmBanner}>
            PLC 1 FAULT — Running on backup PLC 2 ({ip2})
          </div>
        )}

        <div style={s.body}>
          <div style={s.leftPanel}>
            <div style={s.panelHeader}>Tag Monitor</div>
            <table style={s.table}>
              <thead>
                <tr>
                  <th style={s.th}>Tag</th>
                  <th style={s.th}>Value</th>
                  <th style={s.th}>Quality</th>
                  <th style={s.th}>Source</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <TagRow
                    key={r.key}
                    label={r.label}
                    value={tags?.[r.key]}
                    source={r.source}
                    colorRule={r.colorRule}
                    striped={i % 2 === 1}
                  />
                ))}
              </tbody>
            </table>

            <div style={s.controlRow}>
              <button style={s.btnOn} onClick={() => handleControl("on")}>
                Close 52 (ON)
              </button>
              <button style={s.btnOff} onClick={() => handleControl("off")}>
                Trip 52 (OFF)
              </button>
            </div>
            {controlMsg && <div style={s.controlMsg}>{controlMsg}</div>}
          </div>

          <div style={s.rightPanel}>
            <div style={s.panelHeader}>Poll / Diagnostics</div>
            {!polling ? (
              <div style={s.pollRow}>
                <span style={s.pollLabel}>Duration</span>
                <input
                  style={s.pollInput}
                  value={pollDuration}
                  onChange={e => setPollDuration(e.target.value)}
                  type="number"
                  min="1"
                  onKeyDown={e => e.key === "Enter" && handlePoll()}
                />
                <span style={s.pollLabel}>s</span>
                <button style={s.btnPrimarySmall} onClick={handlePoll}>Start poll</button>
              </div>
            ) : (
              <div style={s.pollRow}>
                <span style={s.pollLabel}>Polling · {pollRemaining}s remaining</span>
                <button style={s.btnGraySmall} onClick={stopPoll}>Stop</button>
              </div>
            )}

            <div style={s.diagText}>
              DNP3 class scan: every 5s<br />
              Modbus fallback: PLC2 :504<br />
              Last integrity poll: {lastUpdated || "—"}
            </div>

            {error && <div style={s.errorBox}>{error}</div>}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Tag row ───────────────────────────────────────────────────────────────
function TagRow({ label, value, source, colorRule, striped }) {
  const v = value ?? "—";
  const isErr = v === "ERR";
  const isOn = v === "ON" || v === "CLOSED";

  let valueColor = "#17181a";
  if (!isErr) {
    if (colorRule === "status") {
      valueColor = isOn ? "#3c7a3e" : "#6a6d6e";
    } else if (colorRule === "alarm") {
      valueColor = isOn ? "#b33b2e" : "#3c7a3e";
    } else if (colorRule === "backupAlarm") {
      valueColor = isOn ? "#8a6414" : "#6a6d6e";
    } else if (colorRule === "numeric") {
      valueColor = "#2f6690";
    }
  } else {
    valueColor = "#b33b2e";
  }

  return (
    <tr style={striped ? s.trStriped : s.tr}>
      <td style={s.td}>{label}</td>
      <td style={{ ...s.td, ...s.tdValue, color: valueColor }}>{v}</td>
      <td style={s.td}>
        <span style={isErr ? s.badgeErr : s.badgeGood}>
          {isErr ? "ERR" : "GOOD"}
        </span>
      </td>
      <td style={{ ...s.td, ...s.tdSource }}>{source}</td>
    </tr>
  );
}

// ── Styles ───────────────────────────────────────────────────────────────
const s = {
  page: {
    minHeight: "100vh",
    background: "#e5e5e2",
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "center",
    fontFamily: "'IBM Plex Sans', 'Segoe UI', system-ui, sans-serif",
    padding: 24,
  },
  frame: {
    background: "#efeeea",
    border: "1px solid #b8bab6",
    borderRadius: 2,
    width: "100%",
    maxWidth: 960,
    overflow: "hidden",
  },
  loginCard: {
    background: "#efeeea",
    border: "1px solid #b8bab6",
    borderRadius: 2,
    padding: 36,
    width: 380,
    display: "flex",
    flexDirection: "column",
    gap: 14,
  },
  loginTitle: {
    fontSize: 20,
    fontWeight: 700,
    color: "#17181a",
    letterSpacing: "0.02em",
  },
  loginSub: {
    fontSize: 13,
    color: "#6a6d6e",
    marginTop: -8,
  },
  divider: {
    height: 1,
    background: "#cfd1cd",
  },
  header: {
    background: "#2c2e2f",
    color: "#e8e8e6",
    padding: "12px 18px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    fontSize: 13,
    fontWeight: 600,
    letterSpacing: "0.02em",
    borderTop: "3px solid #2f6690",
  },
  headerRight: {
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: 11,
    color: "#a9a9a6",
    fontWeight: 400,
  },
  disconnectLink: {
    cursor: "pointer",
    textDecoration: "underline",
  },
  alarmBanner: {
    background: "#5a2a20",
    color: "#f0968c",
    padding: "10px 18px",
    fontSize: 12,
    fontWeight: 600,
    letterSpacing: "0.03em",
  },
  body: {
    display: "grid",
    gridTemplateColumns: "1.4fr 1fr",
    gap: 18,
    padding: 18,
  },
  leftPanel: {
    background: "#ffffff",
    border: "1px solid #cfd1cd",
  },
  rightPanel: {
    background: "#ffffff",
    border: "1px solid #cfd1cd",
    padding: 16,
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  panelHeader: {
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    color: "#6a6d6e",
    fontWeight: 500,
    padding: "12px 16px",
    borderBottom: "1px solid #e2e3df",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: 13,
  },
  th: {
    textAlign: "left",
    fontSize: 10,
    textTransform: "uppercase",
    letterSpacing: "0.04em",
    color: "#8a8c88",
    fontWeight: 500,
    padding: "8px 16px",
    borderBottom: "1px solid #e2e3df",
  },
  tr: {
    background: "#ffffff",
  },
  trStriped: {
    background: "#fafaf8",
  },
  td: {
    padding: "10px 16px",
    borderBottom: "1px solid #eeefec",
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: 13,
  },
  tdValue: {
    fontWeight: 600,
  },
  tdSource: {
    color: "#8a8c88",
    fontSize: 11,
  },
  badgeGood: {
    fontFamily: "'IBM Plex Sans', sans-serif",
    fontSize: 10,
    fontWeight: 500,
    background: "#e3ecdf",
    color: "#3c5a3e",
    padding: "2px 8px",
    borderRadius: 2,
  },
  badgeErr: {
    fontFamily: "'IBM Plex Sans', sans-serif",
    fontSize: 10,
    fontWeight: 500,
    background: "#f5e0dc",
    color: "#8a3524",
    padding: "2px 8px",
    borderRadius: 2,
  },
  controlRow: {
    display: "flex",
    gap: 10,
    padding: 16,
  },
  btnOn: {
    fontFamily: "'IBM Plex Sans', sans-serif",
    fontSize: 13,
    fontWeight: 500,
    padding: "9px 16px",
    borderRadius: 2,
    border: "1px solid #8fae86",
    background: "#eef3ec",
    color: "#2e4a2a",
    cursor: "pointer",
  },
  btnOff: {
    fontFamily: "'IBM Plex Sans', sans-serif",
    fontSize: 13,
    fontWeight: 500,
    padding: "9px 16px",
    borderRadius: 2,
    border: "1px solid #c99a8d",
    background: "#f6ece9",
    color: "#7a3524",
    cursor: "pointer",
  },
  controlMsg: {
    fontSize: 12,
    color: "#6a6d6e",
    padding: "0 16px 14px",
  },
  pollRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexWrap: "wrap",
  },
  pollLabel: {
    fontSize: 12,
    color: "#6a6d6e",
  },
  pollInput: {
    fontFamily: "'IBM Plex Mono', monospace",
    width: 50,
    padding: "6px 8px",
    border: "1px solid #cfd1cd",
    borderRadius: 2,
  },
  btnPrimary: {
    fontFamily: "'IBM Plex Sans', sans-serif",
    fontSize: 14,
    fontWeight: 600,
    padding: "10px 18px",
    borderRadius: 2,
    border: "1px solid #2f6690",
    background: "#2f6690",
    color: "#fff",
    cursor: "pointer",
  },
  btnPrimarySmall: {
    fontFamily: "'IBM Plex Sans', sans-serif",
    fontSize: 12,
    fontWeight: 500,
    padding: "6px 14px",
    borderRadius: 2,
    border: "1px solid #2f6690",
    background: "#2f6690",
    color: "#fff",
    cursor: "pointer",
  },
  btnGraySmall: {
    fontFamily: "'IBM Plex Sans', sans-serif",
    fontSize: 12,
    fontWeight: 500,
    padding: "6px 14px",
    borderRadius: 2,
    border: "1px solid #cfd1cd",
    background: "#efeeea",
    color: "#3a3c3d",
    cursor: "pointer",
  },
  diagText: {
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: 11,
    color: "#8a8c88",
    lineHeight: 1.7,
    borderTop: "1px solid #e2e3df",
    paddingTop: 12,
  },
  input: {
    background: "#ffffff",
    border: "1px solid #cfd1cd",
    borderRadius: 2,
    padding: "10px 14px",
    color: "#17181a",
    fontSize: 14,
    outline: "none",
    width: "100%",
    boxSizing: "border-box",
  },
  fieldLabel: {
    fontSize: 12,
    color: "#6a6d6e",
    fontWeight: 500,
  },
  errorBox: {
    color: "#8a3524",
    fontSize: 12,
    background: "#f5e0dc",
    border: "1px solid #d9b3a8",
    borderRadius: 2,
    padding: "8px 12px",
  },
  hint: {
    fontSize: 11,
    color: "#a9a9a6",
    textAlign: "center",
  },
};
