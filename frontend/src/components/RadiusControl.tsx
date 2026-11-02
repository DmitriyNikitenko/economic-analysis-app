import { useEffect, useState } from "react";
import type { Domain, LayerConfig } from "../layers";

type DomainConfig = LayerConfig["domains"][number];

// Настройка радиуса досягаемости для одного экономического домена
// Ползунок и текстовое поле синхронизированы
export default function RadiusControl({
  domain,
  onChange,
}: {
  domain: DomainConfig;
  onChange: (domain: Domain, radiusKm: number) => void;
}) {
  // Храним временное значение радиуса в текстовом поле, чтобы пользователь мог вводить число вручную
  const [draft, setDraft] = useState(String(domain.radius_km)); 

  // Если радиус изменился ползунком или внешней настройкой, обновляем текстовое поле
  useEffect(() => {
    setDraft(String(domain.radius_km));
  }, [domain.radius_km]);

  // Проверяем введённое значение, нормализуем его и вызываем onChange, если оно корректно
  function commitDraft() {
    const normalized = draft.trim().replace(",", ".");
    const parsed = Number(normalized);

    if (!normalized || !Number.isFinite(parsed)) {
      setDraft(String(domain.radius_km));
      return;
    }

    // Ограничиваем значение диапазоном ползунка (0-250 км) и округляем к шагу 0.5 км.
    const radius = Math.round(Math.min(250, Math.max(0, parsed)) * 2) / 2;
    setDraft(String(radius));
    onChange(domain.id, radius);
  }

  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <label htmlFor={`radius-${domain.id}`} className="font-medium">
          {domain.label}
        </label>
        <div className="flex items-center gap-2">
          {/* Текстовое поле для ввода радиуса в километрах */}
          <input
            id={`radius-${domain.id}`}
            type="text"
            inputMode="decimal"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={commitDraft}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                commitDraft();
                event.currentTarget.blur();
              }
              if (event.key === "Escape") {
                setDraft(String(domain.radius_km));
                event.currentTarget.blur();
              }
            }}
            aria-label={`Радиус связей: ${domain.label}, километры`}
            className="w-20 rounded-md border border-slate-300 px-2 py-1.5 text-right tabular-nums"
          />

          <span className="text-sm text-slate-500">км</span>
        </div>
      </div>

      {/* Текстовое поле и ползунок синхронизированы: изменение одного обновляет другое. */}
      <input
        type="range"
        min={0}
        max={250}
        step={0.5}
        value={domain.radius_km}
        onChange={(event) => {
          const radius = Number(event.target.value);
          setDraft(String(radius));
          onChange(domain.id, radius);
        }}
        aria-label={`Ползунок радиуса: ${domain.label}`}
        className="w-full cursor-pointer accent-sky-700"
      />

      <div className="mt-1 flex justify-between text-xs text-slate-500">
        <span>0 км</span>
        <span>250 км</span>
      </div>
    </div>
  );
}