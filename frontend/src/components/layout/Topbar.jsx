import { useEffect, useState } from 'react';
import { Bell, LogOut, Menu, ShieldCheck } from 'lucide-react';
import StatusDot from '../common/StatusDot';
import { socket } from '../../services/socket';
import { useAuth } from '../../hooks/useAuth';

const STATUS_DOT = { open: 'online', connecting: 'warning', reconnecting: 'warning', closed: 'offline' };
const STATUS_LABEL = { open: 'Realtime Connected', connecting: 'Connecting...', reconnecting: 'Reconnecting...', closed: 'Realtime Offline' };

export default function Topbar({ onMenuClick }) {
  const { user, logout } = useAuth();
  const [wsStatus, setWsStatus] = useState('closed');

  useEffect(() => socket.onStatusChange(setWsStatus), []);

  const initials = user?.username ? user.username.slice(0, 2).toUpperCase() : '--';

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b bg-sidebar px-4 md:px-6">
      <div className="flex items-center gap-3">
        <button aria-label="Open navigation" onClick={onMenuClick} className="text-secondary hover:text-primary md:hidden">
          <Menu size={20} />
        </button>
        <ShieldCheck size={17} className="text-info" />
        <span className="text-xs font-semibold uppercase tracking-[.15em] text-secondary">Command Center</span>
      </div>
      <div className="flex items-center gap-3 md:gap-5">
        <button className="relative flex items-center gap-2 text-secondary hover:text-primary">
          <Bell size={17} />
        </button>
        <div className="hidden items-center gap-2 border-l pl-4 text-[11px] uppercase tracking-wide text-secondary lg:flex">
          <StatusDot status={STATUS_DOT[wsStatus] || 'offline'} />
          <span>{STATUS_LABEL[wsStatus] || 'Realtime Offline'}</span>
        </div>
        <div className="flex items-center gap-2 border-l pl-3">
          <div className="grid h-7 w-7 place-items-center rounded-sm bg-panelSecondary text-[10px] font-bold text-primary">
            {initials}
          </div>
          <div className="hidden leading-4 sm:block">
            <p className="text-xs font-medium text-primary">{user?.username || 'Operator'}</p>
            <p className="text-[10px] capitalize text-muted">{user?.role || ''}</p>
          </div>
          <button
            aria-label="Log out"
            onClick={logout}
            className="ml-1 text-muted hover:text-primary"
          >
            <LogOut size={15} />
          </button>
        </div>
      </div>
    </header>
  );
}
