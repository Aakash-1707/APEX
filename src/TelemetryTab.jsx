// APEX Telemetry Tab — Track map + driver comparison
import { useState, useEffect, useRef, useCallback } from "react";
import { T, apiFetch, Card, SectionHeader, Tag, Spinner, ErrorBanner } from "./theme";

function LegendItem({ color, label }) {
  return (
    <div style={{display:"flex",alignItems:"center",gap:"8px"}}>
      <div style={{width:"12px",height:"5px",background:color,borderRadius:"1px"}}/>
      <span style={{fontFamily:T.fontMono,fontSize:"8px",letterSpacing:"1.5px",color:T.dim2}}>{label}</span>
    </div>
  );
}

export default function TelemetryTab({ sessionKey, drivers, mode }) {
  const allDrivers = drivers || [];
  const [driverA, setDriverA] = useState(null);
  const [driverB, setDriverB] = useState(null);
  const [telemA, setTelemA] = useState(null);
  const [telemB, setTelemB] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const progressRef = useRef(0);
  const playingRef = useRef(false);
  const animRef = useRef(null);
  const canvasRef = useRef(null);

  // Auto-select first two drivers
  useEffect(() => {
    if (allDrivers.length >= 2 && !driverA) {
      setDriverA(allDrivers[0]?.driver_number);
      setDriverB(allDrivers[1]?.driver_number);
    }
  }, [allDrivers, driverA]);

  // Fetch telemetry
  const fetchTelemetry = useCallback(async () => {
    if (!sessionKey || !driverA || !driverB || mode === "upcoming") return;
    setLoading(true); setError(null);
    try {
      const [tA, tB] = await Promise.all([
        apiFetch(`/telemetry/${sessionKey}/${driverA}`),
        apiFetch(`/telemetry/${sessionKey}/${driverB}`),
      ]);
      setTelemA(tA); setTelemB(tB);
    } catch(e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [sessionKey, driverA, driverB, mode]);

  useEffect(() => { fetchTelemetry(); }, [fetchTelemetry]);

  // Build track points — INVERT Y so it's not mirrored
  const trackPts = telemA?.x?.length > 0
    ? telemA.x.map((x, i) => [x, 1 - telemA.y[i]])
    : null;

  const drawTrack = useCallback((progA, progB) => {
    const canvas = canvasRef.current;
    if (!canvas || !trackPts) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;
    const pad = 40;
    ctx.clearRect(0, 0, W, H);

    // Transform normalized [0-1] to canvas coords with padding + aspect ratio
    const aspect = (W - pad*2) / (H - pad*2);
    const toCanvas = ([x,y]) => [x*(W-pad*2)+pad, y*(H-pad*2)+pad];

    // --- Track outline glow ---
    ctx.save();
    ctx.beginPath();
    trackPts.forEach(([x,y],i) => {
      const [cx,cy] = toCanvas([x,y]);
      i===0 ? ctx.moveTo(cx,cy) : ctx.lineTo(cx,cy);
    });
    ctx.closePath();
    ctx.strokeStyle = "rgba(255,255,255,0.03)";
    ctx.lineWidth = 20;
    ctx.lineJoin = "round"; ctx.lineCap = "round";
    ctx.stroke();
    ctx.strokeStyle = "rgba(255,255,255,0.05)";
    ctx.lineWidth = 10;
    ctx.stroke();
    ctx.restore();

    // --- Speed-colored track ---
    for (let i=0; i<trackPts.length-1; i++) {
      const [x1,y1] = toCanvas(trackPts[i]);
      const [x2,y2] = toCanvas(trackPts[i+1]);
      const spd = telemA?.speed?.[i] || 200;
      let color;
      if (spd < 80) color = "#E63946";        // Heavy braking (Crisp Red)
      else if (spd < 130) color = "#F4A261";   // Braking zone (Warm Orange)
      else if (spd < 180) color = "#E9C46A";   // Low speed (Soft Yellow)
      else if (spd < 250) color = "#2A9D8F";   // Medium speed (Modern Teal)
      else if (spd < 300) color = "#48CAE4";   // High speed (Bright Blue)
      else color = "#FFFFFF";                  // DRS/straight (Pure White)

      ctx.beginPath();
      ctx.moveTo(x1,y1); ctx.lineTo(x2,y2);
      ctx.strokeStyle = color;
      ctx.lineWidth = 5; ctx.lineCap = "round";
      ctx.globalAlpha = 0.7; ctx.stroke();
      ctx.globalAlpha = 1;
    }

    // --- S/F line ---
    if (trackPts[0]) {
      const [fx,fy] = toCanvas(trackPts[0]);
      ctx.save();
      ctx.fillStyle = "#fff"; ctx.globalAlpha = 0.8;
      ctx.fillRect(fx-8,fy-2,16,4);
      ctx.globalAlpha = 1;
      ctx.fillStyle = "#fff"; ctx.font = "bold 9px 'DM Mono'";
      ctx.textAlign = "center"; ctx.textBaseline = "bottom";
      ctx.fillText("S/F", fx, fy - 6);
      ctx.restore();
    }

    // --- Driver trail helper ---
    const drawDriverTrail = (progVal, teamColor, acronym, trailLen) => {
      const nPts = trackPts.length;
      const mainIdx = Math.floor(progVal * (nPts - 1));

      // Trail (last ~15 points)
      for (let t = trailLen; t >= 0; t--) {
        const tIdx = mainIdx - t;
        if (tIdx < 0 || tIdx >= nPts) continue;
        const [tx, ty] = toCanvas(trackPts[tIdx]);
        const alpha = ((trailLen - t) / trailLen) * 0.5;
        const size = 1.5 + ((trailLen - t) / trailLen) * 2;
        ctx.beginPath(); ctx.arc(tx, ty, size, 0, Math.PI*2);
        ctx.fillStyle = teamColor; ctx.globalAlpha = alpha;
        ctx.fill(); ctx.globalAlpha = 1;
      }

      // Main dot
      if (mainIdx >= 0 && mainIdx < nPts) {
        const [dx, dy] = toCanvas(trackPts[mainIdx]);

        // Outer glow
        ctx.beginPath(); ctx.arc(dx, dy, 12, 0, Math.PI*2);
        ctx.fillStyle = teamColor; ctx.globalAlpha = 0.15; ctx.fill();
        ctx.globalAlpha = 1;

        // Inner dot
        ctx.beginPath(); ctx.arc(dx, dy, 6, 0, Math.PI*2);
        ctx.fillStyle = teamColor;
        ctx.shadowColor = teamColor; ctx.shadowBlur = 16;
        ctx.fill();
        ctx.shadowBlur = 0;

        // White ring
        ctx.beginPath(); ctx.arc(dx, dy, 7, 0, Math.PI*2);
        ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.5; ctx.globalAlpha = 0.6;
        ctx.stroke(); ctx.globalAlpha = 1;

        // Label
        ctx.fillStyle = "#fff"; ctx.font = "bold 10px 'DM Mono'";
        ctx.textAlign = "center"; ctx.textBaseline = "bottom";
        ctx.shadowColor = "rgba(0,0,0,0.8)"; ctx.shadowBlur = 4;
        ctx.fillText(acronym, dx, dy - 14);
        ctx.shadowBlur = 0;
      }
    };

    // --- Draw both drivers ---
    const dAInfo = allDrivers.find(d => d.driver_number === driverA);
    const dBInfo = allDrivers.find(d => d.driver_number === driverB);
    const colorA = `#${dAInfo?.team_colour || "27F4D2"}`;
    const colorB = `#${dBInfo?.team_colour || "e8002d"}`;

    drawDriverTrail(progB, colorB, dBInfo?.name_acronym || "", 12);
    drawDriverTrail(progA, colorA, dAInfo?.name_acronym || "", 15);

    // --- Legend ---
    const legend = [
      ["#ff1744","HEAVY BRAKE"],["#e8002d","BRAKING"],["#448aff","LOW SPEED"],
      ["#27F4D2","MID SPEED"],["#b2ff59","HIGH SPEED"],["#ffd700","MAX/DRS"],
    ];
    legend.forEach(([c,l],i)=>{
      ctx.globalAlpha = 0.8;
      ctx.fillStyle=c; ctx.fillRect(12,12+i*15,8,5);
      ctx.fillStyle="#7a7a9a"; ctx.font="8px 'DM Mono'"; ctx.textAlign="left";
      ctx.fillText(l,24,17+i*15);
      ctx.globalAlpha = 1;
    });
  }, [trackPts, telemA, driverA, driverB, allDrivers]);

  // Chart.js for speed/throttle/brake
  const chartRefs = { speed: useRef(null), throttle: useRef(null), brake: useRef(null) };
  const chartInstances = useRef({});

  useEffect(() => {
    if (!telemA || !telemB) return;
    const script = document.createElement("script");
    script.src = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js";
    script.onload = () => {
      const labels = telemA.speed.map((_, i) => i);
      const dAInfo = allDrivers.find(d => d.driver_number === driverA);
      const dBInfo = allDrivers.find(d => d.driver_number === driverB);
      const cA = `#${dAInfo?.team_colour || "448aff"}`;
      const cB = `#${dBInfo?.team_colour || "e8002d"}`;
      const cfgs = {
        speed: { dA: telemA.speed, dB: telemB.speed, min:50, max:360, u:"km/h" },
        throttle: { dA: telemA.throttle, dB: telemB.throttle, min:0, max:105, u:"%" },
        brake: { dA: telemA.brake, dB: telemB.brake, min:0, max:105, u:"%" },
      };
      Object.entries(cfgs).forEach(([key,cfg]) => {
        if (!chartRefs[key].current || !window.Chart) return;
        chartInstances.current[key]?.destroy?.();
        chartInstances.current[key] = new window.Chart(chartRefs[key].current.getContext("2d"), {
          type:"line", data:{ labels, datasets:[
            {data:cfg.dA, borderColor:cA, borderWidth:1.5, backgroundColor:"transparent", pointRadius:0},
            {data:cfg.dB, borderColor:`${cB}88`, borderWidth:1, backgroundColor:"transparent", pointRadius:0, borderDash:[3,3]},
          ]},
          options:{ responsive:true, maintainAspectRatio:false, animation:false,
            plugins:{ legend:{display:false}, tooltip:{enabled:false} },
            scales:{
              x:{ display:false },
              y:{ grid:{color:"rgba(255,255,255,0.06)"}, min:cfg.min, max:cfg.max,
                  ticks:{color:T.dim2, font:{family:"'DM Mono'",size:9}, callback:v=>`${v}${cfg.u}`} },
            },
          },
        });
      });
      drawTrack(0, 0.03);
    };
    document.head.appendChild(script);
    return () => {
      Object.values(chartInstances.current).forEach(c=>c?.destroy?.());
      try { document.head.removeChild(script); } catch(e) {}
    };
  }, [telemA, telemB, drawTrack, allDrivers, driverA, driverB]);

  // Animation loop — smoother with smaller increment
  useEffect(() => {
    let lastTime = 0;
    const loop = (timestamp) => {
      if (playingRef.current && telemA) {
        const dt = lastTime ? (timestamp - lastTime) / 1000 : 0.016;
        lastTime = timestamp;
        // ~12 seconds for a full lap (0.08 per second)
        progressRef.current = (progressRef.current + dt * 0.08) % 1;
        setProgress(progressRef.current);
        // Driver B slightly behind (simulates ~0.5s gap)
        const gapB = Math.max(0, progressRef.current - 0.015);
        drawTrack(progressRef.current, gapB < 0 ? gapB + 1 : gapB);
      } else {
        lastTime = 0;
      }
      animRef.current = requestAnimationFrame(loop);
    };
    animRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(animRef.current);
  }, [drawTrack, telemA]);

  const togglePlay = () => { playingRef.current = !playingRef.current; setPlaying(p => !p); };
  const reset = () => { playingRef.current = false; setPlaying(false); progressRef.current = 0; setProgress(0); drawTrack(0, 0.03); };

  const idx = telemA ? Math.floor(progress * (telemA.speed.length - 1)) : 0;
  const idxB = telemB ? Math.floor(progress * (telemB.speed.length - 1)) : 0;
  const live = {
    speedA: telemA?.speed?.[idx] || 0, speedB: telemB?.speed?.[idxB] || 0,
    throttleA: telemA?.throttle?.[idx] || 0, throttleB: telemB?.throttle?.[idxB] || 0,
    brakeA: telemA?.brake?.[idx] || 0, brakeB: telemB?.brake?.[idxB] || 0,
    gearA: telemA?.gear?.[idx] || 0, gearB: telemB?.gear?.[idxB] || 0,
  };

  if (mode === "upcoming") return (
    <Card><div style={{textAlign:"center",padding:"40px",fontFamily:T.fontMono,fontSize:"10px",color:T.dim2,letterSpacing:"2px"}}>
      TELEMETRY AVAILABLE AFTER SESSION
    </div></Card>
  );
  if (loading) return <Spinner label="Fetching telemetry from OpenF1..."/>;
  if (error) return <ErrorBanner message={error} onRetry={fetchTelemetry}/>;

  const dAInfo = allDrivers.find(d => d.driver_number === driverA);
  const dBInfo = allDrivers.find(d => d.driver_number === driverB);

  return(
    <div>
      {/* Driver selectors */}
      <div style={{display:"flex",alignItems:"center",gap:"16px",marginBottom:"16px",flexWrap:"wrap"}}>
        <div style={{display:"flex",alignItems:"center",gap:"8px"}}>
          <div style={{width:"3px",height:"18px",background:`#${dAInfo?.team_colour||"448aff"}`,borderRadius:"2px"}}/>
          <select value={driverA||""} onChange={e=>setDriverA(+e.target.value)}
            style={{fontFamily:T.fontMono,fontSize:"11px",background:T.bg3,color:T.text,border:`1px solid ${T.border2}`,
              borderRadius:T.radiusSm,padding:"4px 8px",cursor:"pointer"}}>
            {allDrivers.map(d=><option key={d.driver_number} value={d.driver_number}>{d.name_acronym} — {d.full_name}</option>)}
          </select>
        </div>
        <span style={{color:T.dim,fontSize:"12px"}}>vs</span>
        <div style={{display:"flex",alignItems:"center",gap:"8px"}}>
          <div style={{width:"3px",height:"18px",background:`#${dBInfo?.team_colour||"e8002d"}`,borderRadius:"2px"}}/>
          <select value={driverB||""} onChange={e=>setDriverB(+e.target.value)}
            style={{fontFamily:T.fontMono,fontSize:"11px",background:T.bg3,color:T.text,border:`1px solid ${T.border2}`,
              borderRadius:T.radiusSm,padding:"4px 8px",cursor:"pointer"}}>
            {allDrivers.map(d=><option key={d.driver_number} value={d.driver_number}>{d.name_acronym} — {d.full_name}</option>)}
          </select>
        </div>
        <div style={{flex:1}}/>
        <Tag label={`FASTEST LAP · ${telemA?.lap_time ? telemA.lap_time.toFixed(3)+"s" : "—"}`} color={T.yellow}/>
      </div>

      {/* Track + Live readout */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 300px",gap:"16px",marginBottom:"16px"}}>
        <Card style={{padding:"12px"}}>
          <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:"8px"}}>
            <SectionHeader title="Track map · OpenF1 GPS data"/>
            <div style={{display:"flex",gap:"6px"}}>
              <button onClick={togglePlay} style={{padding:"5px 16px",fontFamily:T.fontMono,fontSize:"9px",
                letterSpacing:"2px",background:playing?"rgba(232,0,45,0.1)":"rgba(0,230,118,0.08)",
                border:`1px solid ${playing?T.red:T.green}`,borderRadius:T.radiusSm,
                color:playing?T.red:T.green,cursor:"pointer",textTransform:"uppercase"}}>
                {playing?"⏸ PAUSE":"▶ PLAY"}
              </button>
              <button onClick={reset} style={{padding:"5px 12px",fontFamily:T.fontMono,fontSize:"9px",
                background:"transparent",border:`1px solid ${T.border2}`,borderRadius:T.radiusSm,
                color:T.dim2,cursor:"pointer",letterSpacing:"2px"}}>↺ RESET</button>
            </div>
          </div>
          <div style={{height:"3px",background:T.dim,borderRadius:"2px",marginBottom:"8px",overflow:"hidden"}}>
            <div style={{width:`${progress*100}%`,height:"100%",background:`linear-gradient(90deg, ${T.red}, #ff6d00)`,
              boxShadow:`0 0 8px ${T.red}`,transition:"width .03s linear"}}/>
          </div>
          <canvas ref={canvasRef} width={600} height={420}
            style={{width:"100%",height:"420px",background:T.bg1,borderRadius:"6px",
              border:`1px solid ${T.border}`}}/>
        </Card>

        <div style={{display:"flex",flexDirection:"column",gap:"8px"}}>
          <SectionHeader title="Live readout"/>
          {[
            {label:"SPEED",vA:live.speedA,vB:live.speedB,unit:"km/h",color:T.blue,max:360},
            {label:"THROTTLE",vA:live.throttleA,vB:live.throttleB,unit:"%",color:T.green,max:100},
            {label:"BRAKE",vA:live.brakeA,vB:live.brakeB,unit:"%",color:T.red,max:100},
            {label:"GEAR",vA:live.gearA,vB:live.gearB,unit:"",color:T.yellow,max:8},
          ].map(c=>(
            <Card key={c.label} style={{padding:"10px 14px"}}>
              <div style={{fontFamily:T.fontMono,fontSize:"8px",letterSpacing:"3px",color:T.dim2,marginBottom:"5px"}}>{c.label}</div>
              <div style={{display:"flex",alignItems:"baseline",justifyContent:"space-between"}}>
                <span style={{fontFamily:T.fontDisplay,fontSize:"22px",fontWeight:700,color:c.color,lineHeight:1}}>
                  {c.vA}<span style={{fontSize:"10px",color:T.dim2,marginLeft:"2px"}}>{c.unit}</span>
                </span>
                <span style={{fontFamily:T.fontDisplay,fontSize:"15px",fontWeight:500,color:`${c.color}66`}}>
                  {c.vB}<span style={{fontSize:"9px",color:T.dim2,marginLeft:"2px"}}>{c.unit}</span>
                </span>
              </div>
              <div style={{display:"flex",gap:"4px",marginTop:"5px"}}>
                <div style={{flex:1,height:"3px",background:T.dim,borderRadius:"1px",overflow:"hidden"}}>
                  <div style={{width:`${Math.min(100,(c.vA/c.max)*100)}%`,height:"100%",background:c.color,
                    borderRadius:"1px",transition:"width .05s"}}/>
                </div>
                <div style={{flex:1,height:"3px",background:T.dim,borderRadius:"1px",overflow:"hidden"}}>
                  <div style={{width:`${Math.min(100,(c.vB/c.max)*100)}%`,height:"100%",background:`${c.color}66`,
                    borderRadius:"1px",transition:"width .05s"}}/>
                </div>
              </div>
            </Card>
          ))}
          <div style={{display:"flex",flexDirection:"column",gap:"6px",background:"rgba(0,0,0,0.4)",padding:"10px",borderRadius:"4px",border:`1px solid ${T.border}`}}>
              <LegendItem color="#E63946" label="HEAVY BRAKE"/>
              <LegendItem color="#F4A261" label="BRAKING"/>
              <LegendItem color="#E9C46A" label="LOW SPEED"/>
              <LegendItem color="#2A9D8F" label="MID SPEED"/>
              <LegendItem color="#48CAE4" label="HIGH SPEED"/>
              <LegendItem color="#FFFFFF" label="MAX/DRS"/>
            </div>
        </div>
      </div>

      {/* Trace charts */}
      {[
        {key:"speed",label:"SPEED",unit:"km/h",color:"#448aff",h:100},
        {key:"throttle",label:"THROTTLE",unit:"%",color:"#00e676",h:72},
        {key:"brake",label:"BRAKE",unit:"%",color:T.red,h:72},
      ].map(tr=>(
        <Card key={tr.key} style={{padding:"12px 16px",marginBottom:"8px"}}>
          <div style={{display:"flex",alignItems:"center",gap:"8px",marginBottom:"8px"}}>
            <div style={{width:"3px",height:"14px",background:tr.color,borderRadius:"2px"}}/>
            <span style={{fontFamily:T.fontMono,fontSize:"9px",letterSpacing:"3px",color:T.dim2,textTransform:"uppercase"}}>{tr.label} · {tr.unit}</span>
            <div style={{flex:1}}/>
            <span style={{fontFamily:T.fontMono,fontSize:"9px",color:`#${dAInfo?.team_colour||"448aff"}`}}>— {dAInfo?.name_acronym||""}</span>
            <span style={{fontFamily:T.fontMono,fontSize:"9px",color:`#${dBInfo?.team_colour||"e8002d"}88`,marginLeft:"8px"}}>
              - - {dBInfo?.name_acronym||""}
            </span>
          </div>
          <div style={{height:`${tr.h}px`}}><canvas ref={chartRefs[tr.key]}/></div>
        </Card>
      ))}
    </div>
  );
}
