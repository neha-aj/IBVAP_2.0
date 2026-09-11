import { NavLink } from 'react-router-dom';
import { LayoutDashboard, MonitorPlay, Video, BellRing, History, FileVideo, ChartNoAxesCombined, CarFront, UserRound, Settings, X } from 'lucide-react';
import StatusDot from '../common/StatusDot';
import { useAlerts } from '../../hooks/useAlerts';
import { useSystemHealth } from '../../hooks/useSystemHealth';

function SystemStatus(){
  const {isChecking,isOperational,downServices}=useSystemHealth();
  if(isChecking) return <div className="mt-2 flex gap-2"><StatusDot status="warning"/><div><p className="text-[11px] font-semibold uppercase tracking-wide text-muted">Checking...</p><p className="mt-1 text-[11px] leading-4 text-muted">Contacting backend services</p></div></div>;
  if(isOperational) return <div className="mt-2 flex gap-2"><StatusDot status="online"/><div><p className="text-[11px] font-semibold uppercase tracking-wide text-success">Operational</p><p className="mt-1 text-[11px] leading-4 text-muted">All systems functioning normally</p></div></div>;
  return <div className="mt-2 flex gap-2"><StatusDot status="danger"/><div><p className="text-[11px] font-semibold uppercase tracking-wide text-danger">Degraded</p><p className="mt-1 text-[11px] leading-4 text-muted">{downServices.join(', ')} not responding</p></div></div>;
}

export default function Sidebar({open=false,onClose=()=>{}}){
  const {alerts}=useAlerts();
  const activeAlertCount=alerts.filter(a=>a.status==='active').length;
  const groups=[{label:'Overview',items:[['Dashboard','/',LayoutDashboard]]},{label:'Surveillance',items:[['Live Surveillance','/surveillance',MonitorPlay],['Cameras','/cameras',Video],['Alerts','/alerts',BellRing,activeAlertCount||undefined],['Events','/events',History]]},{label:'Investigation',items:[['Evidence','/evidence',FileVideo],['License Plates','/anpr',CarFront],['Person & Vehicle Search','/reid',UserRound]]},{label:'Analytics',items:[['Analytics','/analytics',ChartNoAxesCombined]]},{label:'System',items:[['Settings','/settings',Settings]]}];
  return <><button aria-label="Close menu overlay" onClick={onClose} className={`fixed inset-0 z-30 bg-black/60 md:hidden ${open?'block':'hidden'}`}/><aside className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r bg-sidebar transition-transform md:static md:translate-x-0 ${open?'translate-x-0':'-translate-x-full'}`}><div className="flex items-start justify-between border-b px-5 py-5"><div><p className="text-xl font-bold tracking-[.08em] text-primary">IBVAP</p><p className="mt-1 max-w-40 text-[10px] uppercase leading-4 tracking-[.14em] text-secondary">Intelligent Border<br/>Video Analytics Platform</p></div><button onClick={onClose} className="text-secondary md:hidden"><X size={18}/></button></div><nav className="flex-1 overflow-y-auto p-3">{groups.map(group=><div key={group.label} className="mb-5"><p className="eyebrow mb-2 px-3">{group.label}</p>{group.items.map(([label,path,Icon,count])=><NavLink onClick={onClose} end={path==='/'} key={path} to={path} className={({isActive})=>`mb-1 flex items-center gap-3 rounded-sm border-l-2 px-3 py-2.5 text-[13px] ${isActive?'border-info bg-info/10 text-info':'border-transparent text-secondary hover:bg-panelSecondary hover:text-primary'}`}><Icon size={16}/><span className="flex-1">{label}</span>{count&&<span className="rounded-sm bg-danger/15 px-1.5 py-0.5 text-[10px] font-bold text-danger">{count}</span>}</NavLink>)}</div>)}</nav><div className="m-3 border-t pt-4"><p className="eyebrow">System Status</p><SystemStatus/></div></aside></>
}
