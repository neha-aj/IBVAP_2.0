import { useState } from 'react';
import Sidebar from '../components/layout/Sidebar'; import Topbar from '../components/layout/Topbar';
export default function DashboardLayout({children}){const [menuOpen,setMenuOpen]=useState(false);return <div className="flex h-screen overflow-hidden bg-ink"><Sidebar open={menuOpen} onClose={()=>setMenuOpen(false)}/><div className="flex min-w-0 flex-1 flex-col"><Topbar onMenuClick={()=>setMenuOpen(true)}/><main className="min-w-0 flex-1 overflow-y-auto p-5 md:p-6 lg:p-7">{children}</main></div></div>}
