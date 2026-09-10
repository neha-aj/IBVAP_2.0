export default function Modal({open,children}){return open?<div className="fixed inset-0 grid place-items-center bg-black/60 p-4">{children}</div>:null}
