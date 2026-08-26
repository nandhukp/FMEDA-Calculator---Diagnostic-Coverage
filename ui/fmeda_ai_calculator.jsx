import { useState, useCallback, useRef } from "react";

// ── Design tokens ────────────────────────────────────────────────────────────
// Palette: deep navy instrument panel + amber safety warning + signal green pass
// Typeface: monospaced data readouts + clean sans labels
// Signature: the "live gauge" SPFM/LFM meters that animate as you edit data

const C = {
  bg:        "#0D1117",
  panel:     "#161B22",
  panelBdr:  "#21262D",
  panelHi:   "#1C2128",
  amber:     "#E6A817",
  amberDim:  "#7A5A0C",
  green:     "#3FB950",
  greenDim:  "#1A4A24",
  red:       "#F85149",
  redDim:    "#4A1515",
  blue:      "#58A6FF",
  blueDim:   "#0D2A5E",
  muted:     "#8B949E",
  text:      "#E6EDF3",
  textDim:   "#C9D1D9",
  mono:      "'JetBrains Mono', 'Fira Code', 'Courier New', monospace",
  sans:      "'Inter', 'Segoe UI', system-ui, sans-serif",
};

// ── FMEDA Engine (mirrors the Python logic exactly) ─────────────────────────
function calcFMEDA(modes) {
  const safe = modes.filter(m => !m.isSafetyRelated);
  const dangerous = modes.filter(m => m.isSafetyRelated);
  const spfModes = dangerous.filter(m => !m.isLatent);
  const latentModes = dangerous.filter(m => m.isLatent);

  const λTotal     = modes.reduce((s,m) => s + m.lambda, 0);
  const λSafe      = safe.reduce((s,m) => s + m.lambda, 0);
  const λDangerous = dangerous.reduce((s,m) => s + m.lambda, 0);
  const λSPFuncov  = spfModes.reduce((s,m) => s + m.lambda*(1-m.dc), 0);
  const λLatTotal  = latentModes.reduce((s,m) => s + m.lambda, 0);
  const λLatUncov  = latentModes.reduce((s,m) => s + m.lambda*(1-m.dc), 0);

  const spfm = λDangerous > 0 ? 1 - λSPFuncov/λDangerous : 1;
  const lfm  = λLatTotal  > 0 ? 1 - λLatUncov/λLatTotal  : 1;
  const pmhf = λSPFuncov + λLatUncov/2; // FIT

  return { λTotal, λSafe, λDangerous, λSPFuncov, λLatTotal, λLatUncov, spfm, lfm, pmhf };
}

const ASIL_TARGETS = {
  A: { spfm: null, lfm: null,  pmhf: 1000 },
  B: { spfm: 0.90, lfm: 0.60,  pmhf: 100  },
  C: { spfm: 0.97, lfm: 0.80,  pmhf: 10   },
  D: { spfm: 0.99, lfm: 0.90,  pmhf: 1    },
};

function passStatus(val, target, higher=true) {
  if (target === null || target === undefined) return "na";
  return higher ? val >= target : val <= target;
}

// ── Tiny UI atoms ─────────────────────────────────────────────────────────────
const css = (obj) => Object.entries(obj).map(([k,v])=>`${k.replace(/[A-Z]/g,c=>'-'+c.toLowerCase())}:${v}`).join(';');

function Badge({ status }) {
  const map = { true: [C.green, C.greenDim,"PASS"], false: [C.red, C.redDim,"FAIL"], na: [C.muted,"#1a1a1a","N/A"] };
  const [col, bg, label] = map[String(status)] || map.na;
  return (
    <span style={{ fontFamily:C.mono, fontSize:11, fontWeight:700, padding:"2px 7px",
      borderRadius:4, background:bg, color:col, border:`1px solid ${col}44`, letterSpacing:1 }}>
      {label}
    </span>
  );
}

function GaugeBar({ value, target, max=1 }) {
  const pct = Math.min(value/max, 1)*100;
  const tpct = target ? Math.min(target/max,1)*100 : null;
  const color = target === null ? C.blue : value >= target ? C.green : C.red;
  return (
    <div style={{ position:"relative", height:8, background:C.panelBdr, borderRadius:4, overflow:"visible", margin:"4px 0 8px" }}>
      <div style={{ position:"absolute", left:0, top:0, height:"100%", width:`${pct}%`,
        background:color, borderRadius:4, transition:"width 0.4s cubic-bezier(.4,0,.2,1)" }}/>
      {tpct !== null && (
        <div style={{ position:"absolute", top:-3, left:`${tpct}%`, width:2, height:14,
          background:C.amber, borderRadius:1 }}/>
      )}
    </div>
  );
}

function Input({ label, value, onChange, type="number", small=false, unit="" }) {
  return (
    <div style={{ marginBottom:8 }}>
      <label style={{ fontFamily:C.sans, fontSize:11, color:C.muted, display:"block", marginBottom:3, textTransform:"uppercase", letterSpacing:.5 }}>
        {label}
      </label>
      <div style={{ display:"flex", alignItems:"center", gap:4 }}>
        <input type={type} value={value} onChange={e=>onChange(e.target.value)}
          style={{ fontFamily:C.mono, fontSize:13, background:C.panelBdr, border:`1px solid ${C.panelBdr}`,
            color:C.text, padding:"5px 8px", borderRadius:4, width:small?"80px":"100%",
            outline:"none", transition:"border .15s" }}
          onFocus={e=>e.target.style.border=`1px solid ${C.blue}`}
          onBlur={e=>e.target.style.border=`1px solid ${C.panelBdr}`}
        />
        {unit && <span style={{ fontFamily:C.mono, fontSize:11, color:C.muted }}>{unit}</span>}
      </div>
    </div>
  );
}

function Toggle({ label, checked, onChange }) {
  return (
    <label style={{ display:"flex", alignItems:"center", gap:8, cursor:"pointer", userSelect:"none" }}>
      <div onClick={onChange} style={{ width:32, height:18, borderRadius:9, background:checked?C.blue:C.panelBdr,
        position:"relative", transition:"background .2s", cursor:"pointer", flexShrink:0 }}>
        <div style={{ position:"absolute", top:2, left:checked?14:2, width:14, height:14,
          borderRadius:"50%", background:C.text, transition:"left .2s" }}/>
      </div>
      <span style={{ fontFamily:C.sans, fontSize:12, color:C.textDim }}>{label}</span>
    </label>
  );
}

// ── AI Agent Panel ────────────────────────────────────────────────────────────
function AIPanel({ modes, asil, result, onApplySuggestions }) {
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState(null);
  const [mode, setMode] = useState("analyze");

  const prompts = {
    analyze: `You are an ISO 26262 functional safety expert. Analyze this FMEDA data and provide a concise expert assessment.

FMEDA Data:
- ASIL Target: ${asil}
- SPFM: ${result ? (result.spfm*100).toFixed(1) : 0}% (target: ${ASIL_TARGETS[asil].spfm ? (ASIL_TARGETS[asil].spfm*100)+'%' : 'N/A'})
- LFM: ${result ? (result.lfm*100).toFixed(1) : 0}% (target: ${ASIL_TARGETS[asil].lfm ? (ASIL_TARGETS[asil].lfm*100)+'%' : 'N/A'})  
- PMHF: ${result ? result.pmhf.toFixed(2) : 0} FIT (target: <${ASIL_TARGETS[asil].pmhf} FIT)
- Failure modes: ${JSON.stringify(modes.map(m=>({name:m.name,component:m.component,lambda:m.lambda,dc:m.dc,isLatent:m.isLatent,isSafetyRelated:m.isSafetyRelated})))}

Provide: 1) Coverage gap analysis 2) Top 3 weakest failure modes by DC contribution 3) Specific safety mechanism recommendations to close gaps. Be concise and quantitative.`,

    suggest: `You are an ISO 26262 FMEDA expert. Based on this architecture and current failure modes, suggest 3 additional failure modes that are commonly missed.

Current components: ${[...new Set(modes.map(m=>m.component))].join(', ')}
ASIL Target: ${asil}
Current modes: ${modes.map(m=>m.name).join(', ')}

Return ONLY valid JSON array (no markdown, no backticks) with exactly 3 objects, each having: name(string), component(string), lambda(number, FIT), dc(number, 0-1), isLatent(boolean), isSafetyRelated(boolean), rationale(string).`,

    fta: `You are an ISO 26262 safety expert. Generate a concise Fault Tree Analysis (FTA) top-level structure for this FMEDA.

Architecture: ASIL ${asil} system
Failure modes contributing to SPF (undetected): ${modes.filter(m=>m.isSafetyRelated && !m.isLatent && m.dc < 0.99).map(m=>`${m.name} (λ=${m.lambda}FIT, DC=${(m.dc*100).toFixed(0)}%)`).join('; ')}

Provide: 1) Top event definition 2) Gate structure (AND/OR) with 3-4 key branches 3) Minimum cut sets 4) Calculated top event probability in FIT. Format as structured text, not JSON.`,

    closure: `You are an ISO 26262 safety case expert. Generate a safety case closure argument for this FMEDA.

FMEDA Results:
- SPFM: ${result ? (result.spfm*100).toFixed(1) : 0}%  
- LFM: ${result ? (result.lfm*100).toFixed(1) : 0}%
- PMHF: ${result ? result.pmhf.toFixed(2) : 0} FIT
- ASIL Target: ${asil}

Generate: 1) GSN (Goal Structuring Notation) top claim 2) Strategy 3) Sub-claims with evidence requirements 4) Assumptions 5) Open points if any metrics fail. Be specific about what test evidence is needed per claim.`
  };

  const modeLabels = {
    analyze: "Gap Analysis",
    suggest: "Suggest Modes",
    fta: "Gen FTA",
    closure: "Safety Case"
  };

  async function runAgent() {
    setLoading(true);
    setResponse(null);
    try {
      const res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "claude-sonnet-4-6",
          max_tokens: 1000,
          messages: [{ role: "user", content: prompts[mode] }]
        })
      });
      const data = await res.json();
      const text = data.content?.[0]?.text || "No response";

      if (mode === "suggest") {
        try {
          const clean = text.replace(/```json|```/g,"").trim();
          const suggestions = JSON.parse(clean);
          setResponse({ type: "suggestions", data: suggestions });
        } catch {
          setResponse({ type: "text", data: text });
        }
      } else {
        setResponse({ type: "text", data: text });
      }
    } catch (e) {
      setResponse({ type: "text", data: `Error: ${e.message}` });
    }
    setLoading(false);
  }

  return (
    <div style={{ background:C.panelHi, border:`1px solid ${C.panelBdr}`, borderRadius:8, padding:16 }}>
      <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:12 }}>
        <div style={{ display:"flex", alignItems:"center", gap:8 }}>
          <div style={{ width:8, height:8, borderRadius:"50%", background:C.amber, boxShadow:`0 0 6px ${C.amber}` }}/>
          <span style={{ fontFamily:C.sans, fontSize:13, fontWeight:600, color:C.text }}>AI Safety Agent</span>
        </div>
      </div>

      <div style={{ display:"flex", gap:6, marginBottom:12, flexWrap:"wrap" }}>
        {Object.entries(modeLabels).map(([k,v]) => (
          <button key={k} onClick={()=>setMode(k)}
            style={{ fontFamily:C.sans, fontSize:11, padding:"4px 10px", borderRadius:4, cursor:"pointer",
              background: mode===k ? C.blueDim : C.panelBdr,
              border:`1px solid ${mode===k ? C.blue : C.panelBdr}`,
              color: mode===k ? C.blue : C.muted, transition:"all .15s" }}>
            {v}
          </button>
        ))}
      </div>

      <button onClick={runAgent} disabled={loading || modes.length===0}
        style={{ width:"100%", padding:"8px 0", fontFamily:C.mono, fontSize:12, fontWeight:700,
          background: loading ? C.panelBdr : C.blueDim, color: loading ? C.muted : C.blue,
          border:`1px solid ${loading ? C.panelBdr : C.blue}`, borderRadius:4, cursor: loading ? "wait" : "pointer",
          transition:"all .15s", letterSpacing:.5 }}>
        {loading ? "⟳  RUNNING AGENT..." : `▶  RUN ${modeLabels[mode].toUpperCase()}`}
      </button>

      {response && (
        <div style={{ marginTop:12 }}>
          {response.type === "suggestions" ? (
            <div>
              <div style={{ fontFamily:C.sans, fontSize:11, color:C.amber, marginBottom:8, textTransform:"uppercase", letterSpacing:.5 }}>
                Suggested failure modes to add:
              </div>
              {response.data.map((s,i) => (
                <div key={i} style={{ background:C.panelBdr, borderRadius:6, padding:10, marginBottom:8,
                  border:`1px solid ${C.amberDim}` }}>
                  <div style={{ fontFamily:C.mono, fontSize:12, color:C.amber, marginBottom:4 }}>
                    {s.name} — {s.component}
                  </div>
                  <div style={{ fontFamily:C.mono, fontSize:11, color:C.muted, marginBottom:6 }}>
                    λ={s.lambda} FIT  DC={((s.dc||0)*100).toFixed(0)}%
                    {s.isLatent?" · Latent":""}  {!s.isSafetyRelated?" · Safe":""}
                  </div>
                  <div style={{ fontFamily:C.sans, fontSize:11, color:C.textDim, marginBottom:8 }}>
                    {s.rationale}
                  </div>
                  <button onClick={()=>onApplySuggestions([s])}
                    style={{ fontFamily:C.mono, fontSize:10, padding:"3px 8px", borderRadius:3, cursor:"pointer",
                      background:C.greenDim, border:`1px solid ${C.green}`, color:C.green }}>
                    + ADD TO FMEDA
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ background:C.panelBdr, borderRadius:6, padding:12, marginTop:8 }}>
              <pre style={{ fontFamily:C.sans, fontSize:12, color:C.textDim, whiteSpace:"pre-wrap",
                lineHeight:1.6, margin:0, maxHeight:320, overflowY:"auto" }}>
                {response.data}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Mode Row Component ─────────────────────────────────────────────────────────
function ModeRow({ mode, idx, onUpdate, onDelete }) {
  const dcColor = mode.dc >= 0.99 ? C.green : mode.dc >= 0.90 ? C.amber : C.red;
  const [expanded, setExpanded] = useState(false);

  return (
    <div style={{ background:C.panelBdr, borderRadius:6, padding:"10px 12px", marginBottom:6,
      border:`1px solid ${expanded ? C.blue+"44" : "transparent"}`, transition:"border .2s" }}>
      {/* Collapsed row */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 140px 80px 70px 60px 30px", alignItems:"center", gap:8 }}>
        <div>
          <div style={{ fontFamily:C.mono, fontSize:12, color:C.text }}>{mode.name || "–"}</div>
          <div style={{ fontFamily:C.sans, fontSize:10, color:C.muted }}>{mode.component || "–"}</div>
        </div>
        <div style={{ display:"flex", gap:6 }}>
          {mode.isLatent && <span style={{ fontFamily:C.mono, fontSize:9, color:C.amber, border:`1px solid ${C.amberDim}`, padding:"1px 5px", borderRadius:3 }}>LATENT</span>}
          {!mode.isSafetyRelated && <span style={{ fontFamily:C.mono, fontSize:9, color:C.muted, border:`1px solid ${C.panelBdr}`, padding:"1px 5px", borderRadius:3 }}>SAFE</span>}
          {mode.isSafetyRelated && !mode.isLatent && <span style={{ fontFamily:C.mono, fontSize:9, color:C.red, border:`1px solid ${C.redDim}`, padding:"1px 5px", borderRadius:3 }}>SPF</span>}
        </div>
        <div style={{ fontFamily:C.mono, fontSize:12, color:C.text, textAlign:"right" }}>{mode.lambda} <span style={{ fontSize:9, color:C.muted }}>FIT</span></div>
        <div style={{ fontFamily:C.mono, fontSize:12, color:dcColor, textAlign:"right" }}>{(mode.dc*100).toFixed(0)}%</div>
        <div style={{ fontFamily:C.mono, fontSize:11, color:C.muted, textAlign:"right" }}>
          {mode.isSafetyRelated ? (mode.lambda*(1-mode.dc)).toFixed(2) : "—"}
        </div>
        <div style={{ display:"flex", gap:4 }}>
          <button onClick={()=>setExpanded(e=>!e)}
            style={{ background:"none", border:"none", color:C.muted, cursor:"pointer", fontSize:14, padding:0 }}>
            {expanded ? "▲" : "▼"}
          </button>
          <button onClick={()=>onDelete(idx)}
            style={{ background:"none", border:"none", color:C.redDim, cursor:"pointer", fontSize:14, padding:0, lineHeight:1 }}>
            ×
          </button>
        </div>
      </div>

      {/* Expanded editor */}
      {expanded && (
        <div style={{ marginTop:12, paddingTop:12, borderTop:`1px solid ${C.panelBdr}`,
          display:"grid", gridTemplateColumns:"1fr 1fr", gap:"0 16px" }}>
          <Input label="Failure Mode Name" value={mode.name}
            onChange={v=>onUpdate(idx,{name:v})} type="text"/>
          <Input label="Component" value={mode.component}
            onChange={v=>onUpdate(idx,{component:v})} type="text"/>
          <Input label="Failure Rate" value={mode.lambda}
            onChange={v=>onUpdate(idx,{lambda:parseFloat(v)||0})} small unit="FIT"/>
          <Input label="Diagnostic Coverage" value={mode.dc}
            onChange={v=>onUpdate(idx,{dc:Math.min(1,Math.max(0,parseFloat(v)||0))})} small unit="(0–1)"/>
          <div style={{ display:"flex", flexDirection:"column", gap:8, marginTop:4 }}>
            <Toggle label="Latent / Multi-point fault" checked={mode.isLatent}
              onChange={()=>onUpdate(idx,{isLatent:!mode.isLatent})}/>
            <Toggle label="Safety-related (dangerous)" checked={mode.isSafetyRelated}
              onChange={()=>onUpdate(idx,{isSafetyRelated:!mode.isSafetyRelated})}/>
          </div>
          {mode.isSafetyRelated && (
            <div style={{ background:C.panel, borderRadius:4, padding:8, alignSelf:"start" }}>
              <div style={{ fontFamily:C.mono, fontSize:10, color:C.muted, marginBottom:4 }}>UNCOVERED λ CONTRIBUTION</div>
              <div style={{ fontFamily:C.mono, fontSize:18, color:dcColor }}>
                {(mode.lambda*(1-mode.dc)).toFixed(3)} <span style={{ fontSize:10 }}>FIT</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main App ───────────────────────────────────────────────────────────────────
const DEFAULT_MODES = [
  { id:1, name:"CPU lockstep mismatch", component:"Safety MCU (ASIL D)", lambda:10, dc:0.99, isLatent:false, isSafetyRelated:true },
  { id:2, name:"DRAM ECC uncorrectable", component:"Compute SoC (ASIL B)", lambda:20, dc:0.97, isLatent:false, isSafetyRelated:true },
  { id:3, name:"FSI heartbeat timeout", component:"Compute SoC (ASIL B)", lambda:25, dc:0.99, isLatent:false, isSafetyRelated:true },
  { id:4, name:"GPU silent inference error", component:"Compute SoC GPU", lambda:40, dc:0.86, isLatent:false, isSafetyRelated:true },
  { id:5, name:"IOMMU fault latent", component:"Compute SoC (ASIL B)", lambda:8,  dc:0.90, isLatent:true,  isSafetyRelated:true },
  { id:6, name:"Camera power supervisor FAULT pin stuck", component:"Camera Power Supervisor", lambda:8,  dc:0.97, isLatent:false, isSafetyRelated:true },
  { id:7, name:"PCIe C2C silent corruption", component:"PCIe C2C", lambda:12, dc:0.99, isLatent:false, isSafetyRelated:true },
  { id:8, name:"Status LED fault", component:"Board", lambda:5,  dc:0,    isLatent:false, isSafetyRelated:false },
  { id:9, name:"IMU slow drift (latent)", component:"IMU", lambda:5,  dc:0.80, isLatent:true,  isSafetyRelated:true },
  { id:10,name:"Companion SBC voltage monitor fault", component:"Companion SBC (ASIL D)", lambda:7,  dc:0.95, isLatent:false, isSafetyRelated:true },
];

let nextId = 100;

export default function FMEDACalculator() {
  const [modes, setModes] = useState(DEFAULT_MODES);
  const [asil, setAsil] = useState("D");
  const [activeTab, setActiveTab] = useState("fmeda");

  const result = calcFMEDA(modes);
  const targets = ASIL_TARGETS[asil];

  const spfmPass = passStatus(result.spfm, targets.spfm, true);
  const lfmPass  = passStatus(result.lfm,  targets.lfm,  true);
  const pmhfPass = passStatus(result.pmhf, targets.pmhf, false);

  const addMode = () => {
    setModes(m => [...m, { id:nextId++, name:"New failure mode", component:"Component",
      lambda:10, dc:0.9, isLatent:false, isSafetyRelated:true }]);
  };

  const updateMode = (idx, patch) => setModes(m => m.map((x,i)=>i===idx?{...x,...patch}:x));
  const deleteMode = (idx) => setModes(m => m.filter((_,i)=>i!==idx));

  const applySuggestions = (suggestions) => {
    setModes(m => [...m, ...suggestions.map(s => ({
      id:nextId++, name:s.name, component:s.component,
      lambda:s.lambda||10, dc:s.dc||0.9,
      isLatent:s.isLatent||false, isSafetyRelated:s.isSafetyRelated!==false
    }))]);
  };

  const loadPreset = (preset) => {
    if (preset === "adas") setModes(DEFAULT_MODES);
    if (preset === "mcu") setModes([
      { id:nextId++, name:"CPU compute error", component:"MCU core", lambda:18, dc:0.99, isLatent:false, isSafetyRelated:true },
      { id:nextId++, name:"RAM bit error", component:"MCU RAM", lambda:12, dc:0.97, isLatent:false, isSafetyRelated:true },
      { id:nextId++, name:"Program hang", component:"MCU", lambda:6, dc:0.99, isLatent:false, isSafetyRelated:true },
      { id:nextId++, name:"Status LED fault", component:"Board", lambda:5, dc:0, isLatent:false, isSafetyRelated:false },
      { id:nextId++, name:"Supervisor ERR pin stuck", component:"PMIC", lambda:3, dc:0.90, isLatent:true, isSafetyRelated:true },
    ]);
  };

  const tabs = [
    { id:"fmeda", label:"FMEDA Table" },
    { id:"metrics", label:"Metrics" },
    { id:"agent", label:"AI Agent" },
    { id:"guide", label:"Input Guide" },
  ];

  return (
    <div style={{ background:C.bg, minHeight:"100vh", fontFamily:C.sans, color:C.text, padding:0 }}>
      {/* Header */}
      <div style={{ background:C.panel, borderBottom:`1px solid ${C.panelBdr}`, padding:"12px 24px",
        display:"flex", alignItems:"center", justifyContent:"space-between", flexWrap:"wrap", gap:8 }}>
        <div>
          <div style={{ display:"flex", alignItems:"center", gap:10 }}>
            <div style={{ fontFamily:C.mono, fontSize:10, color:C.amber, letterSpacing:2, padding:"2px 6px",
              border:`1px solid ${C.amberDim}`, borderRadius:3 }}>ISO 26262</div>
            <span style={{ fontFamily:C.mono, fontSize:16, fontWeight:700, color:C.text }}>FMEDA Calculator</span>
            <span style={{ fontFamily:C.sans, fontSize:11, color:C.muted }}>+ AI Safety Agent</span>
          </div>
          <div style={{ fontFamily:C.sans, fontSize:11, color:C.muted, marginTop:2 }}>
            Single-Point Fault Metric · Latent Fault Metric · PMHF · FTA Support
          </div>
        </div>
        <div style={{ display:"flex", alignItems:"center", gap:12 }}>
          <div style={{ fontFamily:C.sans, fontSize:11, color:C.muted }}>ASIL Target:</div>
          {["A","B","C","D"].map(a => (
            <button key={a} onClick={()=>setAsil(a)}
              style={{ fontFamily:C.mono, fontSize:13, fontWeight:700, width:36, height:36,
                borderRadius:6, cursor:"pointer", transition:"all .15s",
                background: asil===a ? (a==="D"?C.redDim:a==="C"?C.amberDim:C.blueDim) : C.panelBdr,
                border:`2px solid ${asil===a ? (a==="D"?C.red:a==="C"?C.amber:C.blue) : C.panelBdr}`,
                color: asil===a ? (a==="D"?C.red:a==="C"?C.amber:C.blue) : C.muted }}>
              {a}
            </button>
          ))}
        </div>
      </div>

      {/* Live metric bar */}
      <div style={{ background:C.panelHi, borderBottom:`1px solid ${C.panelBdr}`,
        padding:"10px 24px", display:"flex", gap:24, flexWrap:"wrap" }}>
        {[
          { label:"SPFM", val:`${(result.spfm*100).toFixed(2)}%`, target:targets.spfm ? `≥${(targets.spfm*100).toFixed(0)}%`:null, pass:spfmPass },
          { label:"LFM",  val:`${(result.lfm*100).toFixed(2)}%`,  target:targets.lfm  ? `≥${(targets.lfm*100).toFixed(0)}%`:null,  pass:lfmPass  },
          { label:"PMHF", val:`${result.pmhf.toFixed(3)} FIT`, target:targets.pmhf ? `≤${targets.pmhf} FIT`:null, pass:pmhfPass },
          { label:"λ Total", val:`${result.λTotal.toFixed(1)} FIT`, target:null, pass:"na" },
        ].map(m => (
          <div key={m.label} style={{ minWidth:140 }}>
            <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:2 }}>
              <span style={{ fontFamily:C.mono, fontSize:10, color:C.muted, textTransform:"uppercase", letterSpacing:1 }}>{m.label}</span>
              <Badge status={m.pass}/>
            </div>
            <div style={{ fontFamily:C.mono, fontSize:18, fontWeight:700,
              color: m.pass===true ? C.green : m.pass===false ? C.red : C.blue }}>
              {m.val}
            </div>
            {m.target && <div style={{ fontFamily:C.mono, fontSize:10, color:C.muted }}>target {m.target}</div>}
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display:"flex", gap:0, borderBottom:`1px solid ${C.panelBdr}`, background:C.panel, padding:"0 24px" }}>
        {tabs.map(t => (
          <button key={t.id} onClick={()=>setActiveTab(t.id)}
            style={{ fontFamily:C.sans, fontSize:12, padding:"10px 16px", background:"none", cursor:"pointer",
              border:"none", borderBottom:`2px solid ${activeTab===t.id ? C.blue : "transparent"}`,
              color: activeTab===t.id ? C.blue : C.muted, transition:"all .15s" }}>
            {t.label}
          </button>
        ))}
      </div>

      <div style={{ padding:"16px 24px", maxWidth:1400, margin:"0 auto" }}>

        {/* ── FMEDA Table Tab ── */}
        {activeTab === "fmeda" && (
          <div>
            {/* Toolbar */}
            <div style={{ display:"flex", gap:8, marginBottom:12, flexWrap:"wrap" }}>
              <button onClick={addMode}
                style={{ fontFamily:C.mono, fontSize:11, padding:"6px 14px", borderRadius:4, cursor:"pointer",
                  background:C.greenDim, border:`1px solid ${C.green}`, color:C.green }}>
                + ADD FAILURE MODE
              </button>
              <button onClick={()=>loadPreset("adas")}
                style={{ fontFamily:C.mono, fontSize:11, padding:"6px 14px", borderRadius:4, cursor:"pointer",
                  background:C.blueDim, border:`1px solid ${C.blue}`, color:C.blue }}>
                LOAD: ADAS Platform
              </button>
              <button onClick={()=>loadPreset("mcu")}
                style={{ fontFamily:C.mono, fontSize:11, padding:"6px 14px", borderRadius:4, cursor:"pointer",
                  background:C.blueDim, border:`1px solid ${C.blue}`, color:C.blue }}>
                LOAD: Safety MCU
              </button>
            </div>

            {/* Column headers */}
            <div style={{ display:"grid", gridTemplateColumns:"1fr 140px 80px 70px 60px 30px",
              gap:8, padding:"0 12px 6px", marginBottom:4 }}>
              {["Failure Mode / Component","Classification","λ (FIT)","DC","Uncov λ",""].map((h,i) => (
                <div key={i} style={{ fontFamily:C.mono, fontSize:10, color:C.muted, textTransform:"uppercase", letterSpacing:.5 }}>{h}</div>
              ))}
            </div>

            {modes.map((m,i) => (
              <ModeRow key={m.id} mode={m} idx={i} onUpdate={updateMode} onDelete={deleteMode}/>
            ))}

            {/* Totals row */}
            <div style={{ background:C.panelHi, borderRadius:6, padding:"10px 12px", marginTop:8,
              border:`1px solid ${C.panelBdr}`, display:"grid",
              gridTemplateColumns:"1fr 140px 80px 70px 60px 30px", gap:8, alignItems:"center" }}>
              <div style={{ fontFamily:C.mono, fontSize:11, color:C.muted, textTransform:"uppercase", letterSpacing:1 }}>TOTALS</div>
              <div/>
              <div style={{ fontFamily:C.mono, fontSize:12, color:C.text, textAlign:"right" }}>
                {result.λTotal.toFixed(1)} <span style={{ fontSize:9, color:C.muted }}>FIT</span>
              </div>
              <div/>
              <div style={{ fontFamily:C.mono, fontSize:12, color:C.red, textAlign:"right" }}>
                {(result.λSPFuncov + result.λLatUncov).toFixed(3)}
              </div>
              <div/>
            </div>
          </div>
        )}

        {/* ── Metrics Tab ── */}
        {activeTab === "metrics" && (
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:16, maxWidth:900 }}>
            {/* SPFM Card */}
            <div style={{ background:C.panel, border:`1px solid ${C.panelBdr}`, borderRadius:8, padding:20 }}>
              <div style={{ display:"flex", justifyContent:"space-between", marginBottom:12 }}>
                <div>
                  <div style={{ fontFamily:C.mono, fontSize:10, color:C.muted, letterSpacing:1 }}>SINGLE POINT FAULT METRIC</div>
                  <div style={{ fontFamily:C.mono, fontSize:28, fontWeight:700,
                    color: spfmPass===true ? C.green : spfmPass===false ? C.red : C.blue }}>
                    {(result.spfm*100).toFixed(2)}%
                  </div>
                </div>
                <Badge status={spfmPass}/>
              </div>
              <GaugeBar value={result.spfm} target={targets.spfm}/>
              <div style={{ fontFamily:C.mono, fontSize:10, color:C.muted }}>
                Formula: 1 − (λ_SPF_uncovered / λ_dangerous)
              </div>
              <div style={{ fontFamily:C.mono, fontSize:11, color:C.textDim, marginTop:8 }}>
                λ_SPF_uncov = {result.λSPFuncov.toFixed(3)} FIT
              </div>
              <div style={{ fontFamily:C.mono, fontSize:11, color:C.textDim }}>
                λ_dangerous = {result.λDangerous.toFixed(3)} FIT
              </div>
            </div>

            {/* LFM Card */}
            <div style={{ background:C.panel, border:`1px solid ${C.panelBdr}`, borderRadius:8, padding:20 }}>
              <div style={{ display:"flex", justifyContent:"space-between", marginBottom:12 }}>
                <div>
                  <div style={{ fontFamily:C.mono, fontSize:10, color:C.muted, letterSpacing:1 }}>LATENT FAULT METRIC</div>
                  <div style={{ fontFamily:C.mono, fontSize:28, fontWeight:700,
                    color: lfmPass===true ? C.green : lfmPass===false ? C.red : C.blue }}>
                    {(result.lfm*100).toFixed(2)}%
                  </div>
                </div>
                <Badge status={lfmPass}/>
              </div>
              <GaugeBar value={result.lfm} target={targets.lfm}/>
              <div style={{ fontFamily:C.mono, fontSize:10, color:C.muted }}>
                Formula: 1 − (λ_latent_uncov / λ_latent_total)
              </div>
              <div style={{ fontFamily:C.mono, fontSize:11, color:C.textDim, marginTop:8 }}>
                λ_latent_uncov = {result.λLatUncov.toFixed(3)} FIT
              </div>
              <div style={{ fontFamily:C.mono, fontSize:11, color:C.textDim }}>
                λ_latent_total = {result.λLatTotal.toFixed(3)} FIT
              </div>
            </div>

            {/* PMHF Card */}
            <div style={{ background:C.panel, border:`1px solid ${C.panelBdr}`, borderRadius:8, padding:20 }}>
              <div style={{ display:"flex", justifyContent:"space-between", marginBottom:12 }}>
                <div>
                  <div style={{ fontFamily:C.mono, fontSize:10, color:C.muted, letterSpacing:1 }}>PMHF</div>
                  <div style={{ fontFamily:C.mono, fontSize:28, fontWeight:700,
                    color: pmhfPass===true ? C.green : C.red }}>
                    {result.pmhf.toFixed(3)} <span style={{ fontSize:14 }}>FIT</span>
                  </div>
                </div>
                <Badge status={pmhfPass}/>
              </div>
              <GaugeBar value={targets.pmhf/(result.pmhf||0.001)} target={1} max={2}/>
              <div style={{ fontFamily:C.mono, fontSize:10, color:C.muted }}>
                Formula: λ_SPF_uncov + λ_latent_uncov/2
              </div>
              <div style={{ fontFamily:C.mono, fontSize:11, color:C.textDim, marginTop:8 }}>
                Target for ASIL {asil}: ≤ {targets.pmhf} FIT ({targets.pmhf}×10⁻⁹/hr)
              </div>
            </div>

            {/* Breakdown Card */}
            <div style={{ background:C.panel, border:`1px solid ${C.panelBdr}`, borderRadius:8, padding:20 }}>
              <div style={{ fontFamily:C.mono, fontSize:10, color:C.muted, letterSpacing:1, marginBottom:16 }}>
                FAILURE RATE BREAKDOWN
              </div>
              {[
                { label:"Total λ", val:result.λTotal, color:C.text },
                { label:"Safe faults (excluded)", val:result.λSafe, color:C.muted },
                { label:"Dangerous (total)", val:result.λDangerous, color:C.amber },
                { label:"SPF uncovered", val:result.λSPFuncov, color:C.red },
                { label:"Latent total", val:result.λLatTotal, color:C.blue },
                { label:"Latent uncovered", val:result.λLatUncov, color:C.red },
              ].map(r => (
                <div key={r.label} style={{ display:"flex", justifyContent:"space-between",
                  marginBottom:8, paddingBottom:8, borderBottom:`1px solid ${C.panelBdr}` }}>
                  <span style={{ fontFamily:C.sans, fontSize:12, color:C.muted }}>{r.label}</span>
                  <span style={{ fontFamily:C.mono, fontSize:12, color:r.color }}>{r.val.toFixed(3)} FIT</span>
                </div>
              ))}
            </div>

            {/* Worst offenders */}
            <div style={{ background:C.panel, border:`1px solid ${C.panelBdr}`, borderRadius:8, padding:20, gridColumn:"1/-1" }}>
              <div style={{ fontFamily:C.mono, fontSize:10, color:C.muted, letterSpacing:1, marginBottom:12 }}>
                WORST CONTRIBUTORS — UNCOVERED λ (SPF + LATENT)
              </div>
              {[...modes]
                .filter(m=>m.isSafetyRelated)
                .map(m=>({...m, uncov: m.lambda*(1-m.dc)}))
                .sort((a,b)=>b.uncov-a.uncov)
                .slice(0,5)
                .map((m,i) => (
                  <div key={m.id} style={{ display:"flex", alignItems:"center", gap:12, marginBottom:8 }}>
                    <div style={{ fontFamily:C.mono, fontSize:10, color:C.muted, width:16 }}>#{i+1}</div>
                    <div style={{ flex:1 }}>
                      <div style={{ fontFamily:C.mono, fontSize:11, color:C.text }}>{m.name}</div>
                      <div style={{ height:6, background:C.panelBdr, borderRadius:3, marginTop:4, overflow:"hidden" }}>
                        <div style={{ height:"100%", borderRadius:3, background:i===0?C.red:i===1?C.amber:C.blue,
                          width:`${Math.min(m.uncov/modes.reduce((s,x)=>Math.max(s,x.lambda*(1-x.dc)),0.001)*100,100)}%` }}/>
                      </div>
                    </div>
                    <div style={{ fontFamily:C.mono, fontSize:12, color:C.red, minWidth:80, textAlign:"right" }}>
                      {m.uncov.toFixed(3)} FIT
                    </div>
                    <div style={{ fontFamily:C.mono, fontSize:10, color:C.muted, minWidth:40 }}>
                      DC {(m.dc*100).toFixed(0)}%
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* ── AI Agent Tab ── */}
        {activeTab === "agent" && (
          <div style={{ maxWidth:800 }}>
            <div style={{ background:C.panelHi, border:`1px solid ${C.amberDim}`, borderRadius:8, padding:12, marginBottom:16 }}>
              <div style={{ fontFamily:C.sans, fontSize:12, color:C.amber, marginBottom:4 }}>
                ⚡ AI Safety Agent — Powered by Claude
              </div>
              <div style={{ fontFamily:C.sans, fontSize:11, color:C.textDim, lineHeight:1.6 }}>
                The agent reads your live FMEDA data (ASIL target, all failure modes, DC values, computed metrics)
                and provides expert analysis. Select a mode below and run the agent.
              </div>
            </div>
            <AIPanel modes={modes} asil={asil} result={result} onApplySuggestions={applySuggestions}/>
          </div>
        )}

        {/* ── Input Guide Tab ── */}
        {activeTab === "guide" && (
          <div style={{ maxWidth:900 }}>
            {[
              {
                title: "Source Documents Required",
                color: C.amber,
                items: [
                  ["Component Datasheets", "Failure rate (MTBF/FIT) per component. Source: manufacturer datasheet, component datasheet, SoC supplier Safety Manual, MCU supplier Safety Manual."],
                  ["Failure Rate Databases", "SN 29500 (Siemens — preferred for automotive), IEC TR 62380 (board-level), MIL-HDBK-217F. Use to derive λ_fit per component at rated Tj."],
                  ["FMEA / HAZOP outputs", "System-level hazard log gives you which failure modes are safety-related vs safe. Maps to is_safety_related field."],
                  ["Safety Mechanism Specification", "Your SWRS / HW design spec documents each diagnostic. DC is derived from this — e.g., GMSL CRC spec gives DC=97% for FM-CAM-01."],
                  ["Fault Injection Test Reports", "TC-SOC-01, TC-CAM-xx, TC-PCIE-xx results. These replace estimated DC with validated DC in each row."],
                  ["ISO 26262-5 Safety Manual (component)", "For complex ICs (Compute SoC, Safety MCU), the supplier Safety Manual gives DC values for built-in diagnostics (lockstep, ECC) directly."],
                ]
              },
              {
                title: "How to Derive Each Input Field",
                color: C.blue,
                items: [
                  ["lambda_fit (FIT)", "From SN 29500: look up component category (MCU, ASIC, analog). Apply temperature derating factor for Tj. Use manufacturer MTBF data + SN 29500 category for the component type. Typical: MCU=50 FIT, complex SoC=200 FIT."],
                  ["dc (0.0 – 1.0)", "DC = (λ_detected / λ_total_dangerous). Derive from: (a) datasheet diagnostic spec — e.g., lockstep detects 99% of CPU faults → dc=0.99. (b) Fault injection test — TC-CAM-01 shows ERRB detects 92% of lock-loss events → dc=0.92. Never assert DC without evidence."],
                  ["is_latent = True", "Set for multi-point faults: faults that are dangerous only when combined with a second independent fault. Examples: I2C register corruption (needs second fault to cause hazard), IOMMU fault (detected in next poll cycle). Latent faults contribute to LFM, not SPFM."],
                  ["is_safety_related = False", "Set for faults with no effect on the safety goal (safe faults). Examples: status LED, non-critical logging, display cosmetic faults. These are excluded from both SPFM and LFM denominators — must be justified with evidence, not assumed."],
                ]
              },
              {
                title: "Why This Tool vs Manual FMEDA Spreadsheet",
                color: C.green,
                items: [
                  ["Live metric recomputation", "Every DC value change immediately recalculates SPFM/LFM/PMHF. In a spreadsheet, you must manually trigger recalc and risk formula drift. Here, the Python engine logic is always consistent."],
                  ["Worst-contributor ranking", "Metrics tab automatically surfaces the top-5 uncovered λ contributors — in manual FMEDA you must sort and filter. This directly shows you where to focus safety mechanism effort."],
                  ["AI gap analysis", "AI agent reads the live FMEDA state and identifies DC gaps, suggests missing failure modes, and generates FTA/safety case text in seconds — replacing hours of expert review time."],
                  ["DC validation tracking", "Each row can carry estimated vs validated DC status. Manual spreadsheets have no structured way to track this lifecycle — leading to estimated DC being mistaken for validated at review."],
                  ["Preset architectures", "Pre-loaded ADAS Platform and Safety MCU presets let a new engineer start from a calibrated baseline rather than building from scratch — reducing the risk of omitted failure modes."],
                  ["Formula transparency", "The formula for each metric is displayed alongside the result — eliminating the silent formula error risk that exists in hidden spreadsheet cells."],
                ]
              },
              {
                title: "AI Agent Enhancement Roadmap",
                color: C.amber,
                items: [
                  ["Datasheet Parser Agent", "Feed a component datasheet PDF → agent extracts: component name, MTBF/FIT, diagnostic coverage claims, operating temperature range, and pre-populates failure modes automatically."],
                  ["Test Report Mapper Agent", "Feed fault injection test report (TC-CAM-xx, TC-PCIE-xx) → agent matches test IDs to failure modes and promotes DC from estimated to validated with test evidence reference."],
                  ["FTA Generator Agent", "From current FMEDA table → agent generates complete fault tree with AND/OR gates, calculates minimum cut sets, computes top-event probability, and compares against PMHF target."],
                  ["Safety Case Writer Agent", "From closed FMEDA → agent generates ISO 26262 Part 2 GSN (Goal Structuring Notation) safety case argument including sub-claims, evidence pointers, and open points."],
                  ["Closure Tracker Agent", "Monitors the gap between estimated and validated DC across all rows. Emails or Slacks the safety engineer when validation test results are due or overdue relative to project milestones."],
                ]
              }
            ].map(section => (
              <div key={section.title} style={{ background:C.panel, border:`1px solid ${C.panelBdr}`,
                borderRadius:8, padding:20, marginBottom:12 }}>
                <div style={{ fontFamily:C.mono, fontSize:10, color:section.color, letterSpacing:1.5,
                  textTransform:"uppercase", marginBottom:14, paddingBottom:8, borderBottom:`1px solid ${C.panelBdr}` }}>
                  {section.title}
                </div>
                {section.items.map(([label, desc]) => (
                  <div key={label} style={{ display:"grid", gridTemplateColumns:"220px 1fr", gap:12, marginBottom:12 }}>
                    <div style={{ fontFamily:C.mono, fontSize:11, color:section.color }}>{label}</div>
                    <div style={{ fontFamily:C.sans, fontSize:12, color:C.textDim, lineHeight:1.6 }}>{desc}</div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
