import AppRoutes from './routes/AppRoutes';
import { AuthProvider } from './context/AuthContext';
import { AlertsProvider } from './context/AlertsContext';

export default function App() {
  return (
    <AuthProvider>
      <AlertsProvider>
        <AppRoutes />
      </AlertsProvider>
    </AuthProvider>
  );
}
