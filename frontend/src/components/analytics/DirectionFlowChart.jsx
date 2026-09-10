import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

// Fixed compass order (not whatever order the backend happens to return)
// so the chart always reads the same way regardless of which directions
// currently have data.
const COMPASS_ORDER = ['N','NE','E','SE','S','SW','W','NW'];

export default function DirectionFlowChart({data=[],cameras=[],selectedCamera,onSelectCamera}){
  const byName = Object.fromEntries(data.map((d)=>[d.name,d.value]));
  const ordered = COMPASS_ORDER.map((name)=>({name,value:byName[name]||0}));
  const hasData = data.length>0;
  return <div className="panel p-4">
    <div className="flex items-center justify-between gap-2">
      <div>
        <h2 className="font-semibold">Movement direction flow</h2>
        <p className="mt-1 text-[10px] text-muted">Last hour, by compass direction (N = up the frame)</p>
      </div>
      <select
        value={selectedCamera||''}
        onChange={(e)=>onSelectCamera(e.target.value||null)}
        className="border border-line bg-panelSecondary p-1.5 text-[10px] text-secondary outline-none focus:border-info"
      >
        <option value="">All cameras</option>
        {cameras.map((c)=><option key={c.id} value={c.id}>{c.name}</option>)}
      </select>
    </div>
    <div className="mt-4 h-56">
      {!hasData ? <div className="grid h-full place-items-center text-xs text-muted">No movement recorded in the last hour</div> :
        <ResponsiveContainer><BarChart data={ordered}>
          <XAxis dataKey="name" tick={{fill:'#8294a3',fontSize:11}}/>
          <YAxis tick={{fill:'#8294a3',fontSize:11}}/>
          <Tooltip/>
          <Bar dataKey="value" fill="#a78bfa" radius={[2,2,0,0]}/>
        </BarChart></ResponsiveContainer>}
    </div>
  </div>;
}
