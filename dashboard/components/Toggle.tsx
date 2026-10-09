"use client";

interface Props {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  /** Nonaktifkan interaksi (mis. saat request toggle sedang berjalan). */
  disabled?: boolean;
}

export default function Toggle({ checked, onChange, label, disabled = false }: Props) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      // Hit area ≥44px: button transparan berpading (p-2 → 28+16=44px),
      // margin negatif menjaga layout; track visual tetap h-7 w-12 di dalam.
      className="-m-2 shrink-0 rounded-full p-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-50"
    >
      <span
        aria-hidden="true"
        className={`relative block h-7 w-12 rounded-full transition-colors ${
          checked ? "bg-brand" : "bg-edge"
        }`}
      >
        <span
          className={`absolute top-1 h-5 w-5 rounded-full bg-white transition-all ${
            checked ? "left-6" : "left-1"
          }`}
        />
      </span>
    </button>
  );
}
