export const formatDate=(value)=>new Date(value).toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'});
