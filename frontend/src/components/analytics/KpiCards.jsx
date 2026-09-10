import { Activity, Bell, HardHat, Signal } from 'lucide-react';

function Card({icon,label,value,tone}){return <div className="panel p-4"><div className="flex items-center gap-2 text-muted">{icon}<p className="eyebrow">{label}</p></div><p className={`mt-3 text-2xl font-semibold ${tone}`}>{value}</p></div>}

export default function KpiCards({totalEvents,totalAlerts,avgUptime,ppeViolations}){
  return <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
    <Card icon={<Activity size={16}/>} label="Total Events" value={totalEvents} tone="text-primary"/>
    <Card icon={<Bell size={16}/>} label="Total Alerts" value={totalAlerts} tone="text-danger"/>
    <Card icon={<Signal size={16}/>} label="Avg Camera Uptime" value={`${avgUptime}%`} tone="text-info"/>
    <Card icon={<HardHat size={16}/>} label="PPE Violations" value={ppeViolations} tone="text-warning"/>
  </div>;
}
