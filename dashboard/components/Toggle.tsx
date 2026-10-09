"use client";

interface Props {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}

export default function Toggle({ checked, onChange, label }: Props) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative h-7 w-12 shrink-0 rounded-full transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand ${
        checked ? "bg-brand" : "bg-edge"
      }`}
    >
      <span
        className={`absolute top-1 h-5 w-5 rounded-full bg-white transition-all ${
          checked ? "left-6" : "left-1"
        }`}
      />
    </button>
  );
}
