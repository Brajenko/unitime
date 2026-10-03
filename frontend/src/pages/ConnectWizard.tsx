import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { connectApple, fetchConnection, selectCollections } from "../api";
import type { Connection } from "../types";

type Step = "tiles" | "apple" | "select";

export function ConnectWizard() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>(initialStep(params));
  const [connection, setConnection] = useState<Connection | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(oauthError(params));
  const [pending, setPending] = useState(false);
  const [email, setEmail] = useState("");
  const [appPassword, setAppPassword] = useState("");

  useEffect(() => {
    const connectionId = params.get("connection_id");
    if (!connectionId) {
      return;
    }
    fetchConnection(connectionId)
      .then((payload) => {
        setConnection(payload);
        setSelected(new Set(payload.collections.filter((item) => item.selected).map((item) => item.id)));
        setStep("select");
      })
      .catch((reason: Error) => setError(reason.message));
  }, [params]);

  return (
    <div className="page">
      <div className="card wizard">
        <p className="eyebrow">ПОДКЛЮЧЕНИЕ</p>
        <h1 className="wizard-title">Подключить календарь</h1>
        {error ? <p className="error">{error}</p> : null}
        {step === "tiles" ? <Tiles onApple={() => setStep("apple")} /> : null}
        {step === "apple" ? (
          <AppleForm
            email={email}
            appPassword={appPassword}
            pending={pending}
            onEmail={setEmail}
            onPassword={setAppPassword}
            onBack={() => setStep("tiles")}
            onSubmit={(event) => submitApple(event, email, appPassword, setPending, setError, setConnection, setSelected, setStep)}
          />
        ) : null}
        {step === "select" && connection ? (
          <SelectForm
            connection={connection}
            selected={selected}
            pending={pending}
            onToggle={(id) => toggleSelected(id, selected, setSelected)}
            onBack={() => setStep("tiles")}
            onSubmit={() => submitSelect(connection.id, selected, setPending, setError, navigate)}
          />
        ) : null}
      </div>
    </div>
  );
}

function Tiles({ onApple }: { onApple: () => void }) {
  return (
    <div>
      <p className="muted">Выберите сервис. Названия событий мы не сохраняем.</p>
      <div className="tiles">
        <a className="tile" href="/api/connections/google/start">
          Google
        </a>
        <a className="tile" href="/api/connections/yandex/start">
          Яндекс
        </a>
        <button type="button" className="tile" onClick={onApple}>
          Apple
        </button>
      </div>
      <Link className="text-btn" to="/">
        Назад к сетке
      </Link>
    </div>
  );
}

function AppleForm(props: {
  email: string;
  appPassword: string;
  pending: boolean;
  onEmail: (value: string) => void;
  onPassword: (value: string) => void;
  onBack: () => void;
  onSubmit: (event: FormEvent) => void;
}) {
  return (
    <form className="stack" onSubmit={props.onSubmit}>
      <p className="muted">
        У Apple нет входа по OAuth для календаря. Создайте пароль приложения в Apple ID и вставьте его сюда.
      </p>
      <a className="inline-link" href="https://account.apple.com" target="_blank" rel="noreferrer">
        Создать пароль приложения
      </a>
      <label className="field">
        Email Apple ID
        <input value={props.email} onChange={(event) => props.onEmail(event.target.value)} type="email" required />
      </label>
      <label className="field">
        Пароль приложения
        <input
          value={props.appPassword}
          onChange={(event) => props.onPassword(event.target.value)}
          type="password"
          required
          minLength={8}
        />
      </label>
      <div className="row-actions">
        <button type="button" className="text-btn" onClick={props.onBack}>
          Назад
        </button>
        <button type="submit" className="primary" disabled={props.pending}>
          {props.pending ? "Проверяем…" : "Продолжить"}
        </button>
      </div>
    </form>
  );
}

function SelectForm(props: {
  connection: Connection;
  selected: Set<string>;
  pending: boolean;
  onToggle: (id: string) => void;
  onBack: () => void;
  onSubmit: () => void;
}) {
  return (
    <div className="stack">
      <p className="muted">Отметьте календари, из которых брать занятость.</p>
      <ul className="check-list">
        {props.connection.collections.map((item) => (
          <li key={item.id}>
            <label className="check-row">
              <input
                type="checkbox"
                checked={props.selected.has(item.id)}
                onChange={() => props.onToggle(item.id)}
              />
              {item.name}
            </label>
          </li>
        ))}
      </ul>
      <label className="toggle-row">
        <input type="checkbox" checked disabled />
        Показывать только занятость, без названий событий
      </label>
      <div className="row-actions">
        <button type="button" className="text-btn" onClick={props.onBack}>
          Назад
        </button>
        <button type="button" className="primary" disabled={props.pending} onClick={props.onSubmit}>
          {props.pending ? "Подключаем…" : "Подключить"}
        </button>
      </div>
    </div>
  );
}

function initialStep(params: URLSearchParams): Step {
  if (params.get("connection_id") || params.get("step") === "select") {
    return "select";
  }
  return "tiles";
}

function oauthError(params: URLSearchParams): string | null {
  const code = params.get("error");
  if (!code) {
    return null;
  }
  if (code === "oauth") {
    return "Вход отменён.";
  }
  if (code === "state") {
    return "Сессия входа истекла, попробуйте ещё раз.";
  }
  if (code === "google_config") {
    return "В .env не заданы GOOGLE_CLIENT_ID и GOOGLE_CLIENT_SECRET.";
  }
  if (code === "yandex_config") {
    return "В .env не заданы YANDEX_CLIENT_ID и YANDEX_CLIENT_SECRET.";
  }
  return "Не удалось получить доступ к календарю.";
}

function submitApple(
  event: FormEvent,
  email: string,
  appPassword: string,
  setPending: (value: boolean) => void,
  setError: (value: string | null) => void,
  setConnection: (value: Connection) => void,
  setSelected: (value: Set<string>) => void,
  setStep: (value: Step) => void,
) {
  event.preventDefault();
  setPending(true);
  setError(null);
  connectApple(email, appPassword)
    .then((payload) => {
      setConnection(payload);
      setSelected(new Set(payload.collections.filter((item) => item.selected).map((item) => item.id)));
      setStep("select");
    })
    .catch((reason: Error) => setError(reason.message))
    .finally(() => setPending(false));
}

function toggleSelected(id: string, selected: Set<string>, setSelected: (value: Set<string>) => void) {
  const next = new Set(selected);
  if (next.has(id)) {
    next.delete(id);
  } else {
    next.add(id);
  }
  setSelected(next);
}

function submitSelect(
  connectionId: string,
  selected: Set<string>,
  setPending: (value: boolean) => void,
  setError: (value: string | null) => void,
  navigate: ReturnType<typeof useNavigate>,
) {
  setPending(true);
  selectCollections(connectionId, Array.from(selected))
    .then(() => navigate("/"))
    .catch((reason: Error) => setError(reason.message))
    .finally(() => setPending(false));
}
