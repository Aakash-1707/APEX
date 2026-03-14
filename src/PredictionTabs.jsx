// APEX Prediction Tabs — Qualifying + Race — with Actual vs Predicted
import { useState, useEffect } from "react";
import { T, apiFetch, Card, SectionHeader, Tag, Spinner, ErrorBanner } from "./theme";

// Helper to find delta between predicted and actual position
function DeltaBadge({predicted, actual}) {
  if (actual == null) return null;
  const delta = predicted - actual; // positive means predicted worse (higher number) than actual
  const color = delta > 0 ? T.green : delta < 0 ? T.red : T.yellow;
  const text = delta > 0 ? `+${delta}` : delta < 0 ? `${delta}` : "=";
  return (
    <span style={{fontFamily:T.fontMono,fontSize:"10px",fontWeight:700,
      padding:"2px 6px",borderRadius:"3px",
      background:`${color}15`,border:`1px solid ${color}44`,color,
      letterSpacing:"0.5px",minWidth:"28px",textAlign:"center",display:"inline-block"}}>
      {text}
    </span>
  );
}

function humanReadableSource(sourceMode, predictionBasis) {
  if (sourceMode === "fp_only") return "Practice only (no quali data)";
  if (sourceMode === "sprint_quali") return "Sprint qualifying only";
  if (sourceMode === "full_quali") return "Full qualifying result";
  return predictionBasis || "auto";
}

// ─── QUALIFYING PREDICTION TAB ───────────────────────────────────────────────
export function QualiPredictionTab({ sessionKey, drivers, mode, predictions, modelMeta, sourceMode }) {
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (!sessionKey || mode === "upcoming") return;
    apiFetch(`/result/${sessionKey}`).then(setResult).catch(() => {});
  }, [sessionKey, mode]);

  if (!predictions?.length && mode !== "past") return (
    <Card><div style={{textAlign:"center",padding:"40px",fontFamily:T.fontMono,fontSize:"10px",color:T.dim2,letterSpacing:"2px"}}>
      QUALIFYING PREDICTIONS AVAILABLE AFTER MODEL RUN
    </div></Card>
  );
  if (!predictions?.length) return <Spinner label="Loading predictions..."/>;

  const sorted = [...predictions].sort((a,b) => a.grid_pos - b.grid_pos);

  // Build actual results lookup by driver_number
  const actualMap = {};
  if (result) {
    result.forEach(r => {
      actualMap[r.driver_number] = r;
    });
  }

  const hasActual = result && result.length > 0;
  const groups = [
    {label:"Q3 · TOP 10", key:"q3", color:T.red, items:sorted.slice(0,10)},
    {label:"Q2 · P11–15", key:"q2", color:T.yellow, items:sorted.slice(10,15)},
    {label:"Q1 · P16+", key:"q1", color:T.dim2, items:sorted.slice(15)},
  ];

  return(
    <div>
      {hasActual && (
        <div style={{marginBottom:"16px",padding:"10px 14px",
          background:"rgba(0,230,118,0.04)",border:"1px solid rgba(0,230,118,0.2)",
          borderRadius:T.radius,display:"flex",alignItems:"center",gap:"10px"}}>
          <div style={{width:"6px",height:"6px",borderRadius:"50%",background:T.green}}/>
          <span style={{fontFamily:T.fontMono,fontSize:"9px",letterSpacing:"2px",color:T.green}}>
            ACTUAL QUALIFYING RESULT VS PREDICTION · DELTA SHOWS PREDICTION ACCURACY
          </span>
        </div>
      )}
      <Card>
        <div style={{display:"flex",flexDirection:"column",gap:"16px",marginTop:"12px"}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"0 4px"}}>
            <SectionHeader title="Grid prediction · model accuracy"/>
            {modelMeta && (
              <div style={{fontFamily:T.fontMono,fontSize:"10px",color:T.dim2,textTransform:"uppercase"}}>
                DATA SOURCE:{" "}
                <span style={{color:T.accent}}>
                  {humanReadableSource(sourceMode, modelMeta.prediction_basis)}
                </span>
              </div>
            )}
          </div>
          <div style={{display:"flex",gap:"6px"}}>
            <Tag label="100K SIMS" color={T.red}/>
            {hasActual && <Tag label="ACTUAL DATA" color={T.green}/>}
          </div>
        </div>

        {/* Table header */}
        <div style={{display:"flex",alignItems:"center",gap:"10px",padding:"6px 12px",
          borderBottom:`2px solid ${T.border2}`,marginBottom:"4px"}}>
          <span style={{fontFamily:T.fontMono,fontSize:"8px",color:T.dim2,letterSpacing:"2px",width:"45px"}}>PRED</span>
          {hasActual && <span style={{fontFamily:T.fontMono,fontSize:"8px",color:T.green,letterSpacing:"2px",width:"45px"}}>ACTUAL</span>}
          {hasActual && <span style={{fontFamily:T.fontMono,fontSize:"8px",color:T.dim2,letterSpacing:"2px",width:"40px"}}>DELTA</span>}
          <span style={{fontFamily:T.fontMono,fontSize:"8px",color:T.dim2,letterSpacing:"2px",flex:1}}>DRIVER</span>
          <span style={{fontFamily:T.fontMono,fontSize:"8px",color:T.dim2,letterSpacing:"2px",width:"60px",textAlign:"right"}}>WIN %</span>
          <span style={{fontFamily:T.fontMono,fontSize:"8px",color:T.dim2,letterSpacing:"2px",width:"60px",textAlign:"right"}}>SCORE</span>
        </div>

        {groups.map(group=>(
          <div key={group.key} style={{marginBottom:"16px"}}>
            <div style={{marginBottom:"8px",padding:"4px 10px",display:"inline-block",
              borderRadius:"3px",background:`${group.color}11`,
              border:`1px solid ${group.color}33`}}>
              <span style={{fontFamily:T.fontMono,fontSize:"8px",letterSpacing:"2px",color:group.color}}>
                {group.label}
              </span>
            </div>
            {group.items.map(p => {
              const teamColor = p.team_colour ? `#${p.team_colour}` : T.dim;
              const actualResult = actualMap[p.driver_number];
              const actualPos = actualResult?.position;

              return(
                <div key={p.driver} style={{display:"flex",alignItems:"center",gap:"10px",
                  padding:"8px 12px",borderBottom:`1px solid ${T.border}`,
                  transition:"background .1s"}}>
                  {/* Predicted position */}
                  <span style={{fontFamily:T.fontDisplay,fontSize:"14px",fontWeight:700,
                    color:teamColor,width:"45px",textAlign:"center"}}>P{p.grid_pos}</span>

                  {/* Actual position */}
                  {hasActual && (
                    <span style={{fontFamily:T.fontDisplay,fontSize:"14px",fontWeight:700,
                      color:actualPos ? (actualPos <= 3 ? T.green : T.text) : T.dim,
                      width:"45px",textAlign:"center"}}>
                      {actualPos ? `P${actualPos}` : "—"}
                    </span>
                  )}

                  {/* Delta badge */}
                  {hasActual && (
                    <div style={{width:"40px",textAlign:"center"}}>
                      <DeltaBadge predicted={p.grid_pos} actual={actualPos}/>
                    </div>
                  )}

                  {/* Driver info */}
                  <div style={{width:"3px",height:"24px",background:teamColor,borderRadius:"2px"}}/>
                  <div style={{flex:1}}>
                    <div style={{fontFamily:T.fontBody,fontSize:"13px",fontWeight:600,color:T.text}}>{p.driver}</div>
                    <div style={{fontFamily:T.fontMono,fontSize:"9px",color:T.dim2}}>{p.team}</div>
                  </div>

                  {/* Win probability */}
                  <div style={{width:"60px",textAlign:"right"}}>
                    <div style={{fontFamily:T.fontDisplay,fontSize:"14px",fontWeight:700,color:T.yellow}}>
                      {p.win_pct}%
                    </div>
                  </div>

                  {/* Score */}
                  <div style={{width:"60px",textAlign:"right"}}>
                    <div style={{fontFamily:T.fontMono,fontSize:"11px",color:T.blue}}>
                      {p.model_score?.toFixed(4)}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ))}

        {/* Accuracy summary for historical */}
        {hasActual && (() => {
          let totalDelta = 0, count = 0, exact = 0;
          sorted.forEach(p => {
            const actualPos = actualMap[p.driver_number]?.position;
            if (actualPos != null) {
              totalDelta += Math.abs(p.grid_pos - actualPos);
              if (p.grid_pos === actualPos) exact++;
              count++;
            }
          });
          const avgDelta = count > 0 ? (totalDelta / count).toFixed(2) : "—";
          return (
            <div style={{display:"flex",gap:"16px",padding:"12px",marginTop:"12px",
              background:`rgba(0,229,255,0.03)`,border:`1px solid rgba(0,229,255,0.15)`,
              borderRadius:T.radius}}>
              <div>
                <div style={{fontFamily:T.fontMono,fontSize:"8px",letterSpacing:"2px",color:T.dim2}}>AVG DELTA</div>
                <div style={{fontFamily:T.fontDisplay,fontSize:"18px",fontWeight:700,color:"#00e5ff"}}>{avgDelta}</div>
              </div>
              <div>
                <div style={{fontFamily:T.fontMono,fontSize:"8px",letterSpacing:"2px",color:T.dim2}}>EXACT MATCH</div>
                <div style={{fontFamily:T.fontDisplay,fontSize:"18px",fontWeight:700,color:T.green}}>{exact}/{count}</div>
              </div>
              <div>
                <div style={{fontFamily:T.fontMono,fontSize:"8px",letterSpacing:"2px",color:T.dim2}}>TOP 3 ACC</div>
                <div style={{fontFamily:T.fontDisplay,fontSize:"18px",fontWeight:700,color:T.yellow}}>
                  {(() => {
                    const top3Pred = sorted.slice(0,3).map(p => p.driver_number);
                    const top3Actual = result.filter(r => r.position <= 3).map(r => r.driver_number);
                    const matches = top3Pred.filter(dn => top3Actual.includes(dn)).length;
                    return `${matches}/3`;
                  })()}
                </div>
              </div>
            </div>
          );
        })()}
      </Card>
    </div>
  );
}

// ─── RACE PREDICTION TAB ─────────────────────────────────────────────────────
export function RacePredictionTab({ raceSessionKey, drivers, mode, predictions, modelMeta, sourceMode }) {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!raceSessionKey) return;
    setLoading(true);
    apiFetch(`/result/${raceSessionKey}`)
      .then(setResult)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [raceSessionKey]);

  if (!predictions?.length) return <Spinner label="Loading predictions..."/>;

  const sorted = [...predictions].sort((a,b) => b.win_pct - a.win_pct);
  // Show actual vs predicted as soon as a session result exists (works for Sprint + main race)
  const hasActual = result && result.length > 0;

  // Build actual results lookup
  const actualMap = {};
  if (result) {
    result.forEach(r => { actualMap[r.driver_number] = r; });
  }

  return(
    <div>
      {/* Model Info */}
      {modelMeta && (
        <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:"8px",marginBottom:"16px"}}>
          {[
            {l:"SIMULATIONS",v:(modelMeta.n_sims||100000).toLocaleString(),c:T.red},
            {l:"SC PROBABILITY",v:`${((modelMeta.sc_probability||0)*100).toFixed(0)}%`,c:T.yellow},
            {l:"RAIN PROBABILITY",v:`${((modelMeta.rain_probability||0)*100).toFixed(0)}%`,c:T.blue},
            {l:"OVERTAKE FACTOR",v:`${modelMeta.overtake_factor||1.4}x`,c:T.green},
          ].map(m=>(
            <Card key={m.l} style={{padding:"10px 12px"}}>
              <div style={{fontFamily:T.fontMono,fontSize:"8px",letterSpacing:"2px",color:T.dim2,marginBottom:"4px"}}>{m.l}</div>
              <div style={{fontFamily:T.fontDisplay,fontSize:"18px",fontWeight:700,color:m.c}}>{m.v}</div>
            </Card>
          ))}
        </div>
      )}

      {/* Results comparison banner */}
      {hasActual && (
        <div style={{marginBottom:"16px",padding:"10px 14px",
          background:"rgba(0,230,118,0.04)",border:"1px solid rgba(0,230,118,0.2)",
          borderRadius:T.radius,display:"flex",alignItems:"center",gap:"10px"}}>
          <div style={{width:"6px",height:"6px",borderRadius:"50%",background:T.green}}/>
          <span style={{fontFamily:T.fontMono,fontSize:"9px",letterSpacing:"2px",color:T.green}}>
            ACTUAL RACE RESULT VS PREDICTION · DELTA SHOWS MODEL ACCURACY
          </span>
        </div>
      )}

      <Card>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:"16px"}}>
          <SectionHeader title="Race prediction · Monte Carlo results" style={{marginBottom:0}}/>
          {modelMeta && (
            <div style={{fontFamily:T.fontMono,fontSize:"10px",color:T.dim2,textTransform:"uppercase"}}>
              DATA SOURCE:{" "}
              <span style={{color:T.accent}}>
                {humanReadableSource(sourceMode, modelMeta.prediction_basis)}
              </span>
            </div>
          )}
        </div>
        {/* Table header */}
        <div style={{display:"flex",alignItems:"center",gap:"10px",padding:"6px 12px",
          borderBottom:`2px solid ${T.border2}`,marginBottom:"4px"}}>
          <span style={{fontFamily:T.fontMono,fontSize:"8px",color:T.dim2,letterSpacing:"2px",width:"40px"}}>PRED</span>
          {hasActual && <span style={{fontFamily:T.fontMono,fontSize:"8px",color:T.green,letterSpacing:"2px",width:"45px"}}>ACTUAL</span>}
          {hasActual && <span style={{fontFamily:T.fontMono,fontSize:"8px",color:T.dim2,letterSpacing:"2px",width:"40px"}}>DELTA</span>}
          <span style={{fontFamily:T.fontMono,fontSize:"8px",color:T.dim2,letterSpacing:"2px",flex:1}}>DRIVER</span>
          <span style={{fontFamily:T.fontMono,fontSize:"8px",color:T.dim2,letterSpacing:"2px",width:"55px",textAlign:"right"}}>WIN %</span>
          <span style={{fontFamily:T.fontMono,fontSize:"8px",color:T.dim2,letterSpacing:"2px",width:"55px",textAlign:"right"}}>PODIUM</span>
          <span style={{fontFamily:T.fontMono,fontSize:"8px",color:T.dim2,letterSpacing:"2px",width:"55px",textAlign:"right"}}>POINTS</span>
          <span style={{fontFamily:T.fontMono,fontSize:"8px",color:T.dim2,letterSpacing:"2px",width:"45px",textAlign:"right"}}>DNF</span>
        </div>

        {sorted.map((p,i) => {
          const teamColor = p.team_colour ? `#${p.team_colour}` : T.dim;
          const actualResult = actualMap[p.driver_number];
          const actualPos = actualResult?.position;
          const predictedPos = i + 1;

          return(
            <div key={p.driver_number || p.driver} style={{display:"flex",alignItems:"center",gap:"10px",
              padding:"8px 12px",borderBottom:`1px solid ${T.border}`,
              background:i<3?`${teamColor}08`:"transparent"}}>
              {/* Predicted position */}
              <span style={{fontFamily:T.fontDisplay,fontSize:"14px",fontWeight:700,
                color:i<3?T.yellow:T.dim2,width:"40px",textAlign:"center"}}>P{predictedPos}</span>

              {/* Actual position */}
              {hasActual && (
                <span style={{fontFamily:T.fontDisplay,fontSize:"14px",fontWeight:700,
                  color:actualPos && actualPos <= 3 ? T.green : T.text,
                  width:"45px",textAlign:"center"}}>
                  {actualPos ? `P${actualPos}` : "DNF"}
                </span>
              )}

              {/* Delta */}
              {hasActual && (
                <div style={{width:"40px",textAlign:"center"}}>
                  <DeltaBadge predicted={predictedPos} actual={actualPos}/>
                </div>
              )}

              {/* Driver info */}
              <div style={{width:"3px",height:"28px",background:teamColor,borderRadius:"2px"}}/>
              <div style={{flex:1}}>
                <div style={{fontFamily:T.fontBody,fontSize:"13px",fontWeight:600,color:T.text}}>{p.driver}</div>
                <div style={{fontFamily:T.fontMono,fontSize:"9px",color:T.dim2}}>
                  {p.team} · Grid P{p.grid_pos}
                </div>
              </div>

              <div style={{width:"55px",textAlign:"right"}}>
                <span style={{fontFamily:T.fontDisplay,fontSize:"13px",fontWeight:700,
                  color:p.win_pct>10?T.yellow:T.dim2}}>{p.win_pct}%</span>
              </div>
              <div style={{width:"55px",textAlign:"right"}}>
                <span style={{fontFamily:T.fontMono,fontSize:"11px",color:T.blue}}>{p.podium_pct}%</span>
              </div>
              <div style={{width:"55px",textAlign:"right"}}>
                <span style={{fontFamily:T.fontMono,fontSize:"11px",color:T.green}}>{p.points_pct}%</span>
              </div>
              <div style={{width:"45px",textAlign:"right"}}>
                <span style={{fontFamily:T.fontMono,fontSize:"11px",color:p.dnf_pct>10?T.red:T.dim2}}>{p.dnf_pct}%</span>
              </div>
            </div>
          );
        })}

        {/* Accuracy summary */}
        {hasActual && (() => {
          let totalDelta = 0, count = 0, exact = 0;
          sorted.forEach((p,i) => {
            const actualPos = actualMap[p.driver_number]?.position;
            if (actualPos != null) {
              totalDelta += Math.abs((i+1) - actualPos);
              if ((i+1) === actualPos) exact++;
              count++;
            }
          });
          const avgDelta = count > 0 ? (totalDelta / count).toFixed(2) : "—";
          const winner = result.find(r => r.position === 1);
          const predictedWinner = sorted[0];
          const correctWinner = winner?.driver_number === predictedWinner?.driver_number;
          return (
            <div style={{display:"flex",gap:"16px",padding:"12px",marginTop:"12px",
              background:`rgba(0,229,255,0.03)`,border:`1px solid rgba(0,229,255,0.15)`,
              borderRadius:T.radius,flexWrap:"wrap"}}>
              <div>
                <div style={{fontFamily:T.fontMono,fontSize:"8px",letterSpacing:"2px",color:T.dim2}}>AVG POS DELTA</div>
                <div style={{fontFamily:T.fontDisplay,fontSize:"18px",fontWeight:700,color:"#00e5ff"}}>{avgDelta}</div>
              </div>
              <div>
                <div style={{fontFamily:T.fontMono,fontSize:"8px",letterSpacing:"2px",color:T.dim2}}>EXACT MATCH</div>
                <div style={{fontFamily:T.fontDisplay,fontSize:"18px",fontWeight:700,color:T.green}}>{exact}/{count}</div>
              </div>
              <div>
                <div style={{fontFamily:T.fontMono,fontSize:"8px",letterSpacing:"2px",color:T.dim2}}>WINNER PRED</div>
                <div style={{fontFamily:T.fontDisplay,fontSize:"18px",fontWeight:700,
                  color:correctWinner?T.green:T.red}}>
                  {correctWinner ? "✓ CORRECT" : "✗ MISS"}
                </div>
              </div>
              <div>
                <div style={{fontFamily:T.fontMono,fontSize:"8px",letterSpacing:"2px",color:T.dim2}}>TOP 3 ACC</div>
                <div style={{fontFamily:T.fontDisplay,fontSize:"18px",fontWeight:700,color:T.yellow}}>
                  {(() => {
                    const top3Pred = sorted.slice(0,3).map(p => p.driver_number);
                    const top3Actual = result.filter(r => r.position <= 3).map(r => r.driver_number);
                    return `${top3Pred.filter(dn => top3Actual.includes(dn)).length}/3`;
                  })()}
                </div>
              </div>
            </div>
          );
        })()}
      </Card>
    </div>
  );
}
