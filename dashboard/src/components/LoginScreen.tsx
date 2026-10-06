/**
 * Formulario de login nativo: usuario + contraseña contra `POST /auth/login`.
 * Sin secretos en el bundle.
 */

import { useState, type FormEvent } from "react";

export interface LoginScreenProps {
  onSubmit: (username: string, password: string) => Promise<void>;
  error: string | null;
  submitting: boolean;
}

export function LoginScreen({ onSubmit, error, submitting }: LoginScreenProps): JSX.Element {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    await onSubmit(username, password);
  }

  return (
    <main className="flex h-screen flex-col items-center justify-center gap-8 p-8">
      <div className="flex flex-col items-center gap-2 text-center">
        <h1
          className="font-display text-3xl font-semibold uppercase tracking-[0.06em] text-ink"
          translate="no"
        >
          Informe Operativo
        </h1>
        <p className="text-sm text-muted" translate="no">
          Policía de Tucumán — Centro Integrador de Sistemas y Operaciones
        </p>
      </div>
      <form
        onSubmit={handleSubmit}
        className="panel flex w-full max-w-sm flex-col gap-4"
        aria-label="Inicio de sesión"
      >
        <label className="flex flex-col gap-1 text-xs uppercase tracking-wide text-muted">
          Usuario
          <input
            className="touch-target rounded-[10px] border border-border bg-surface2 px-3 text-sm text-ink transition-colors focus-visible:border-accent"
            type="text"
            name="username"
            autoComplete="username"
            spellCheck={false}
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            required
          />
        </label>
        <label className="flex flex-col gap-1 text-xs uppercase tracking-wide text-muted">
          Contraseña
          <input
            className="touch-target rounded-[10px] border border-border bg-surface2 px-3 text-sm text-ink transition-colors focus-visible:border-accent"
            type="password"
            name="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>
        {error ? (
          <p className="text-xs text-neg" role="alert" id="login-error">
            {error}
          </p>
        ) : null}
        <button
          type="submit"
          disabled={submitting}
          aria-describedby={error ? "login-error" : undefined}
          className="touch-target rounded-[10px] border border-accent bg-accent px-3 text-sm font-semibold text-[#04070F] transition-colors hover:bg-accent-bright disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? "Verificando…" : "Entrar"}
        </button>
      </form>
    </main>
  );
}
