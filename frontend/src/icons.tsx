interface IconProps {
  className?: string;
}

function stroke(className?: string) {
  return {
    className,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
}

export function IconSparkle({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <path d="M12 2.6c.35 3.9 2.15 5.7 6.05 6.05-3.9.35-5.7 2.15-6.05 6.05-.35-3.9-2.15-5.7-6.05-6.05C9.85 8.3 11.65 6.5 12 2.6Z" />
      <path d="M18.5 15.2c.2 1.9 1.1 2.8 3 3-1.9.2-2.8 1.1-3 3-.2-1.9-1.1-2.8-3-3 1.9-.2 2.8-1.1 3-3Z" />
    </svg>
  );
}

export function IconPlus({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function IconMenu({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  );
}

export function IconSend({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M12 19V5M6 11l6-6 6 6" />
    </svg>
  );
}

export function IconTrash({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </svg>
  );
}

export function IconClose({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}

export function IconCopy({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <rect x="9" y="9" width="11" height="11" rx="2" />
      <path d="M5 15V5a2 2 0 0 1 2-2h8" />
    </svg>
  );
}

export function IconCheck({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M20 6L9 17l-5-5" />
    </svg>
  );
}

export function IconSun({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

export function IconMoon({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  );
}

export function IconFile({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M14 3v5h5M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
    </svg>
  );
}

export function IconDownload({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M12 4v11M7 11l5 5 5-5M5 20h14" />
    </svg>
  );
}

export function IconExternal({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
    </svg>
  );
}

/** Globo com risco: o modo off (sites sem internet) do botão do topo. */
export function IconGlobeOff({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18" />
      <path d="M12 3a15 15 0 0 1 0 18a15 15 0 0 1 0-18" />
      <path d="M4.5 4.5l15 15" />
    </svg>
  );
}

/** Globo inteiro: o modo online (sites usam CDN) do botão do topo. */
export function IconGlobe({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18" />
      <path d="M12 3a15 15 0 0 1 0 18a15 15 0 0 1 0-18" />
    </svg>
  );
}

export function IconFolder({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    </svg>
  );
}

export function IconGear({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1 7 17M17 7l2.1-2.1" />
    </svg>
  );
}

export function IconSpeaker({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M11 5 6 9H3v6h3l5 4z" />
      <path d="M15.5 8.5a5 5 0 0 1 0 7" />
      <path d="M18.5 5.5a9 9 0 0 1 0 13" />
    </svg>
  );
}

export function IconEye({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6-10-6-10-6z" />
      <circle cx="12" cy="12" r="2.6" />
    </svg>
  );
}

export function IconCode({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M9 18l-6-6 6-6M15 6l6 6-6 6" />
    </svg>
  );
}

export function IconBrain({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M12 5a3 3 0 0 0-6 0 3 3 0 0 0-2 5.2A3 3 0 0 0 6 16a3 3 0 0 0 6 1zM12 5a3 3 0 0 1 6 0 3 3 0 0 1 2 5.2A3 3 0 0 1 18 16a3 3 0 0 1-6 1z" />
    </svg>
  );
}

export function IconChevronDown({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

export function IconBolt({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M13 2L4 14h7l-1 8 9-12h-7z" />
    </svg>
  );
}

export function IconPaperclip({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M21.4 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
    </svg>
  );
}

export function IconMic({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3M8.5 21h7" />
    </svg>
  );
}

/** Ondas sonoras: inicia a conversa por voz (modo hands-free). */
export function IconWaveform({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M2 12h2M7 7v10M12 4v16M17 8v8M22 12h-2" />
    </svg>
  );
}

/** Desligar: encerra a conversa por voz. */
export function IconHangup({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M2.5 13.5c5-5 14-5 19 0l-2 2.5-3.5-1v-2.5a12 12 0 0 0-8 0V15l-3.5 1z" />
    </svg>
  );
}

export function IconStop({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <rect x="6.5" y="6.5" width="11" height="11" rx="2.5" />
    </svg>
  );
}

export function IconPencil({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z" />
    </svg>
  );
}

export function IconRefresh({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M21 12a9 9 0 1 1-2.64-6.36" />
      <path d="M21 4v5h-5" />
    </svg>
  );
}

export function IconSearch({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <circle cx="11" cy="11" r="7" />
      <path d="M20.5 20.5L16.8 16.8" />
    </svg>
  );
}

export function IconImage({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <rect x="3" y="3" width="18" height="18" rx="2.5" />
      <circle cx="8.5" cy="8.5" r="1.6" />
      <path d="M21 15.5l-4.5-4.5L5.5 21" />
    </svg>
  );
}
