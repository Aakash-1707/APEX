// APEX F1 Theme & Shared Components
import { useState, useEffect, useRef } from "react";

export const T = {
  bg0:"#07070a", bg1:"#0c0c12", bg2:"#10101a", bg3:"#1a1a2c", bg4:"#252540",
  red:"#e8002d", redDim:"rgba(232,0,45,0.12)", redBorder:"rgba(232,0,45,0.35)",
  yellow:"#ffd700", green:"#00e676", blue:"#448aff", orange:"#ff6d00", purple:"#d500f9",
  text:"#dde0f0", dim:"#3a3a58", dim2:"#5a5a80",
  border:"#1a1a2c", border2:"#252540",
  fontMono:"'DM Mono','JetBrains Mono','Fira Code',ui-monospace,monospace",
  fontDisplay:"'Orbitron','Rajdhani',sans-serif",
  fontBody:"'Inter',sans-serif",
  radius:"8px", radiusSm:"5px",
  teams:{
    "Mercedes":"#27F4D2","Ferrari":"#ED1131","McLaren":"#F47600",
    "Red Bull Racing":"#4781D7","Aston Martin":"#229971","Alpine":"#00A1E8",
    "Williams":"#1868DB","Haas F1 Team":"#9C9FA2","Kick Sauber":"#52E252",
    "Cadillac":"#909090","Racing Bulls":"#6C98FF","Audi":"#F50537",
    "Red Bull":"#4781D7",
  },
  tyres:{ SOFT:"#FF3333",MEDIUM:"#FFE11A",HARD:"#E8E8E8",INTER:"#39B54A",WET:"#0067FF" },
};

const RENDER_BACKEND = import.meta.env.VITE_API_URL || "";
export const API = `${RENDER_BACKEND}/api`;

export async function apiFetch(path, opts={}) {
  const res = await fetch(`${API}${path}`, opts);
  if (!res.ok) {
    const err = await res.json().catch(()=>({detail: res.statusText}));
    throw new Error(err.detail || `API error ${res.status}`);
  }
  return res.json();
}

export const Tag = ({label,color,bg})=>(
  <span style={{fontSize:"9px",padding:"2px 7px",border:`1px solid ${color||T.border2}`,
    borderRadius:T.radiusSm,color:color||T.dim2,background:bg||"transparent",
    letterSpacing:"1.5px",textTransform:"uppercase",fontFamily:T.fontMono}}>
    {label}
  </span>
);

export const SectionHeader = ({title})=>(
  <div style={{display:"flex",alignItems:"center",gap:"10px",marginBottom:"12px"}}>
    <span style={{fontFamily:T.fontMono,fontSize:"9px",letterSpacing:"4px",
      color:T.red,textTransform:"uppercase",whiteSpace:"nowrap"}}>{title}</span>
    <div style={{flex:1,height:"1px",background:T.border}}/>
  </div>
);

export const Card = ({children,style={}})=>(
  <div style={{background:T.bg2,border:`1px solid ${T.border}`,
    borderRadius:T.radius,padding:"16px",...style}}>
    {children}
  </div>
);

export function Spinner({label="Loading..."}) {
  return(
    <div style={{display:"flex",flexDirection:"column",alignItems:"center",
      justifyContent:"center",gap:"14px",padding:"48px",color:T.dim2}}>
      <div style={{width:"32px",height:"32px",border:`2px solid ${T.border2}`,
        borderTopColor:T.red,borderRadius:"50%",
        animation:"spin .8s linear infinite"}}/>
      <span style={{fontFamily:T.fontMono,fontSize:"9px",letterSpacing:"3px",
        textTransform:"uppercase"}}>{label}</span>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}

export function ErrorBanner({message,onRetry}) {
  return(
    <div style={{padding:"16px 20px",background:"rgba(232,0,45,0.06)",
      border:`1px solid ${T.redBorder}`,borderRadius:T.radius,
      display:"flex",alignItems:"center",gap:"14px"}}>
      <span style={{color:T.red,fontSize:"18px"}}>⚠</span>
      <span style={{fontFamily:T.fontMono,fontSize:"10px",color:T.dim2,flex:1}}>{message}</span>
      {onRetry&&(
        <button onClick={onRetry} style={{padding:"5px 12px",fontFamily:T.fontMono,
          fontSize:"9px",letterSpacing:"2px",background:"transparent",
          border:`1px solid ${T.red}`,borderRadius:T.radiusSm,
          color:T.red,cursor:"pointer",textTransform:"uppercase"}}>
          RETRY
        </button>
      )}
    </div>
  );
}
