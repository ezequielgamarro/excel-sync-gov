/**
 * Composición raíz de la SPA (T47/T49): decide entre el login nativo, la
 * pantalla de acceso denegado y el dashboard de la sala.
 */

import { useAuth } from "./hooks/useAuth";
import { DashboardScreen } from "./screens/DashboardScreen";
import { DeniedScreen } from "./components/DeniedScreen";
import { LoginScreen } from "./components/LoginScreen";

function CenteredMessage({ message }: { message: string }): JSX.Element {
  return (
    <main className="flex h-screen items-center justify-center">
      <p className="text-sm text-muted" role="status" aria-live="polite">
        {message}
      </p>
    </main>
  );
}

export function App(): JSX.Element {
  const auth = useAuth();

  if (auth.status === "checking") return <CenteredMessage message="Verificando sesión…" />;
  if (auth.status === "anonymous" || auth.status === "error") {
    return <LoginScreen onSubmit={auth.login} error={auth.error} submitting={auth.submitting} />;
  }
  if (!auth.canViewLive) return <DeniedScreen />;

  return <DashboardScreen session={auth.session} onLogout={auth.logout} />;
}
