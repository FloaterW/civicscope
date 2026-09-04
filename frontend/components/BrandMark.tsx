type BrandMarkProps = {
  className?: string;
};

/** The CivicScope map-and-lens mark. Pair with visible brand text in headers. */
export function BrandMark({ className = "h-8 w-8" }: BrandMarkProps) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <rect width="32" height="32" rx="7" fill="#0b6864" />
      <path
        d="M7.5 9.6 13 7.4l6 2.2 5.5-2.2v14.9L19 24.5l-6-2.2-5.5 2.2Z"
        fill="none"
        stroke="#fff"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.6"
      />
      <path
        d="M13 7.4v14.9m6-12.7v6.1"
        fill="none"
        stroke="#fff"
        strokeLinecap="round"
        strokeWidth="1.35"
        opacity=".8"
      />
      <circle cx="18.4" cy="17.6" r="3.25" fill="#0b6864" stroke="#fff" strokeWidth="1.6" />
      <path
        d="m20.8 20 2.6 2.6"
        fill="none"
        stroke="#fff"
        strokeLinecap="round"
        strokeWidth="1.7"
      />
    </svg>
  );
}
