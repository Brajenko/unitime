import { FormEvent, useState } from "react";
import { login, register } from "../api";

// После успешного входа App сам переводит на адрес из ?next= (см. LoginRedirect в App.tsx).
export function AuthPage({ onAuthed }: { onAuthed: () => Promise<unknown> }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const action = mode === "login" ? login : register;
    action(email, password)
      .then(() => onAuthed())
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setPending(false));
  }

  return (
    <div className="page">
      <div className="card wizard">
        <p className="eyebrow">{mode === "login" ? "ВХОД" : "РЕГИСТРАЦИЯ"}</p>
        <h1 className="wizard-title">{mode === "login" ? "Войти в сервис" : "Создать аккаунт"}</h1>
        {error ? <p className="error">{error}</p> : null}
        <form className="stack" onSubmit={submit}>
          <label className="field">
            Email
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </label>
          <label className="field">
            Пароль
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={mode === "register" ? 8 : 1}
            />
          </label>
          <div className="row-actions">
            <button
              type="button"
              className="text-btn"
              onClick={() => setMode(mode === "login" ? "register" : "login")}
            >
              {mode === "login" ? "Нет аккаунта? Зарегистрироваться" : "Уже есть аккаунт? Войти"}
            </button>
            <button type="submit" className="primary" disabled={pending}>
              {pending ? "Подождите…" : mode === "login" ? "Войти" : "Зарегистрироваться"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
