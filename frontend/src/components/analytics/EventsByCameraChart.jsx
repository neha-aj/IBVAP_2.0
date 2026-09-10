import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

export default function EventsByCameraChart({data=[],selected,onSelect}){
  return <div className="panel p-4">
    <div className="flex items-center justify-between">
      <h2 className="font-semibold">Events by camera</h2>
      {selected && <button onClick={()=>onSelect(null)} className="text-[10px] text-info hover:underline">Clear filter ({selected})</button>}
    </div>
    <p className="mt-1 text-[10px] text-muted">Click a bar to filter PPE compliance below</p>
    <div className="mt-4 h-56">
      {data.length===0 ? <div className="grid h-full place-items-center text-xs text-muted">No events recorded yet</div> :
        <ResponsiveContainer><BarChart data={data} layout="vertical" margin={{left:8}}>
          <XAxis type="number" tick={{fill:'#8294a3',fontSize:11}}/>
          <YAxis type="category" dataKey="name" width={90} tick={{fill:'#8294a3',fontSize:10}}/>
          <Tooltip/>
          <Bar dataKey="count" radius={[0,2,2,0]} cursor="pointer" onClick={(bar)=>{const name=bar.payload?.name??bar.name;onSelect(selected===name?null:name);}}>
            {data.map((entry,i)=><Cell key={i} fill={selected===entry.name?'#55b7c9':(selected?'#3a4c58':'#55b7c9')} opacity={selected&&selected!==entry.name?0.35:1}/>)}
          </Bar>
        </BarChart></ResponsiveContainer>}
    </div>
  </div>;
}
