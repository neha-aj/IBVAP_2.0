import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

export default function PpeComplianceChart({data=[],filterCamera}){
  const shown = filterCamera ? data.filter((d)=>d.name===filterCamera) : data;
  return <div className="panel p-4">
    <h2 className="font-semibold">PPE compliance</h2>
    <p className="mt-1 text-[10px] text-muted">Violations by camera, requires-PPE zones only{filterCamera && ` — filtered to ${filterCamera}`}</p>
    <div className="mt-4 h-56">
      {shown.length===0 ? <div className="grid h-full place-items-center text-xs text-muted">No PPE violations recorded yet</div> :
        <ResponsiveContainer><BarChart data={shown} layout="vertical" margin={{left:8}}>
          <XAxis type="number" tick={{fill:'#8294a3',fontSize:11}}/>
          <YAxis type="category" dataKey="name" width={90} tick={{fill:'#8294a3',fontSize:10}}/>
          <Tooltip/>
          <Bar dataKey="count" fill="#f59e0b" radius={[0,2,2,0]}/>
        </BarChart></ResponsiveContainer>}
    </div>
  </div>;
}
