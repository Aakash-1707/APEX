// APEX Tyre Degradation Tab
import { useState, useEffect, useRef, useCallback } from "react";
import { T, apiFetch, Card, SectionHeader, Spinner, ErrorBanner } from "./theme";

export default function TyreDegTab({ sessionKey, drivers, mode }) {
  const [stints, setStints] = useState(null);
  const [lapData, setLapData] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const chartRef = useRef(null);
  const chartInst = useRef(null);
  const [activeDrivers, setActiveDrivers] = useState([]);

  const fetchData = useCallback(async () => {
    if (!sessionKey || mode === "upcoming") return;
    setLoading(true); setError(null);
    try {
      const stintData = await apiFetch(`/stints/${sessionKey}`);
      setStints(stintData);

      // Get first 5 drivers by driver number
      const driverNums = Object.keys(stintData).map(Number).slice(0, 5);
      setActiveDrivers(driverNums);

      // Fetch lap data for those drivers
      const laps = {};
      await Promise.all(driverNums.map(async (dn) => {
        try {
          const l = await apiFetch(`/laps/${sessionKey}/${dn}`);
          laps[dn] = l;
        } catch(e) {}
      }));
      setLapData(laps);
    } catch(e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [sessionKey, mode]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Chart rendering
  useEffect(() => {
    if (!stints || !chartRef.current || !drivers?.length) return;
    const script = document.createElement("script");
    script.src = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js";
    script.onload = () => {
      if (!window.Chart) return;

      const maxLap = Math.max(...Object.values(stints).flat().map(s => s.lap_end || 0), 1);
      const labels = Array.from({length: maxLap}, (_, i) => i + 1);

      const datasets = activeDrivers
        .filter(dn => lapData[dn])
        .map((dn, idx) => {
          const d = drivers.find(dr => dr.driver_number === dn);
          const lapTimes = new Array(maxLap).fill(null);
          (lapData[dn] || []).forEach(l => {
            if (l.lap_duration && l.lap_duration > 0 && !l.is_pit_out && l.lap_number <= maxLap) {
              lapTimes[l.lap_number - 1] = l.lap_duration;
            }
          });
          return {
            label: d?.name_acronym || `#${dn}`,
            data: lapTimes,
            borderColor: `#${d?.team_colour || "ffffff"}`,
            borderWidth: 1.5, backgroundColor: "transparent",
            pointRadius: 0, fill: false, tension: 0.3, spanGaps: true,
          };
        });

      chartInst.current?.destroy?.();
      chartInst.current = new window.Chart(chartRef.current.getContext("2d"), {
        type: "line", data: { labels, datasets },
        options: {
          responsive:true, maintainAspectRatio:false, animation:false,
          plugins: {
            legend: { display:true, labels:{color:T.dim2, font:{family:"'DM Mono'",size:9}} },
            tooltip: { bodyFont:{family:"'DM Mono'"}, backgroundColor:T.bg2,
              borderColor:T.border2, borderWidth:1,
              callbacks:{label:c=>`${c.dataset.label}: ${c.parsed.y?.toFixed(3)}s`} },
          },
          scales: {
            x: { grid:{color:"rgba(255,255,255,0.04)"}, ticks:{color:T.dim2,font:{family:"'DM Mono'",size:9}},
                 title:{display:true,text:"LAP",color:T.dim2,font:{family:"'DM Mono'",size:9}} },
            y: { grid:{color:"rgba(255,255,255,0.06)"},
                 ticks:{color:T.dim2,font:{family:"'DM Mono'",size:9},callback:v=>`${v.toFixed(1)}s`},
                 title:{display:true,text:"LAP TIME (s)",color:T.dim2,font:{family:"'DM Mono'",size:9}} },
          },
        },
      });
    };
    document.head.appendChild(script);
    return () => { chartInst.current?.destroy?.(); try{document.head.removeChild(script);}catch(e){} };
  }, [stints, activeDrivers, lapData, drivers]);

  if (mode === "upcoming") return (
    <Card><div style={{textAlign:"center",padding:"40px",fontFamily:T.fontMono,fontSize:"10px",color:T.dim2,letterSpacing:"2px"}}>
      TYRE DATA AVAILABLE AFTER SESSION
    </div></Card>
  );
  if (loading) return <Spinner label="Fetching stint data from OpenF1..."/>;
  if (error) return <ErrorBanner message={error} onRetry={fetchData}/>;
  if (!stints) return null;

  const allDriverNums = Object.keys(stints).map(Number);

  return(
    <div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"16px",marginBottom:"16px"}}>
        <Card>
          <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:"12px",flexWrap:"wrap",gap:"8px"}}>
            <SectionHeader title="Lap time degradation"/>
            <div style={{display:"flex",gap:"4px",flexWrap:"wrap"}}>
              {allDriverNums.slice(0,10).map(dn => {
                const d = drivers?.find(dr => dr.driver_number === dn);
                const active = activeDrivers.includes(dn);
                return(
                  <button key={dn} onClick={async () => {
                    const next = active ? activeDrivers.filter(x=>x!==dn) : [...activeDrivers,dn];
                    setActiveDrivers(next);
                    if (!active && !lapData[dn]) {
                      try {
                        const l = await apiFetch(`/laps/${sessionKey}/${dn}`);
                        setLapData(prev => ({...prev, [dn]: l}));
                      } catch(e) {}
                    }
                  }} style={{
                    padding:"3px 8px",fontFamily:T.fontMono,fontSize:"8px",letterSpacing:"1px",
                    border:`1px solid ${active?`#${d?.team_colour||"e8002d"}`:T.border2}`,
                    borderRadius:T.radiusSm,
                    color:active?`#${d?.team_colour||"e8002d"}`:T.dim,
                    background:active?`#${d?.team_colour||"e8002d"}22`:"transparent",
                    cursor:"pointer",textTransform:"uppercase"}}>
                    {d?.name_acronym || dn}
                  </button>
                );
              })}
            </div>
          </div>
          <div style={{height:"280px"}}><canvas ref={chartRef}/></div>
        </Card>

        <Card>
          <SectionHeader title="Race strategy · tyre compounds"/>
          {allDriverNums.slice(0,10).map(dn => {
            const d = drivers?.find(dr => dr.driver_number === dn);
            const driverStints = stints[dn] || [];
            return(
              <div key={dn} style={{display:"flex",alignItems:"center",gap:"8px",marginBottom:"8px"}}>
                <span style={{fontFamily:T.fontMono,fontSize:"10px",
                  color:T.dim2,width:"40px",flexShrink:0}}>{d?.name_acronym||dn}</span>
                <div style={{flex:1,display:"flex",gap:"2px",height:"20px"}}>
                  {driverStints.map((s,i) => {
                    const compound = (s.compound||"UNKNOWN").toUpperCase();
                    const color = T.tyres[compound] || T.dim;
                    return(
                      <div key={i} style={{
                        flex:s.laps||1, background:color, borderRadius:"3px",
                        display:"flex",alignItems:"center",justifyContent:"center",
                        fontSize:"8px",fontWeight:700,letterSpacing:"0.5px",
                        color:compound==="MEDIUM"||compound==="HARD"?"#000":"#fff",
                        opacity:0.88,fontFamily:T.fontMono}}>
                        {compound[0]}{s.laps}
                      </div>
                    );
                  })}
                </div>
                <span style={{fontFamily:T.fontMono,fontSize:"8px",color:T.dim2,width:"20px"}}>
                  {Math.max(0,driverStints.length-1)}P
                </span>
              </div>
            );
          })}
        </Card>
      </div>
    </div>
  );
}
