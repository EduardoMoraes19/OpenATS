import Image from "next/image";

/**
 * Wave/particle texture and the cascading "F" vector shapes are the two
 * graphic elements the Featcode brand manual calls out as reusable
 * background motifs (not the logo itself, which is never recomposed) -
 * approximated here in inline SVG since the manual's own texture files are
 * high-res renders, not something to embed as a raster asset.
 */
function BrandTexture() {
  return (
    <svg
      className="absolute inset-0 h-full w-full"
      viewBox="0 0 800 1000"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="wave-fade" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#25E2AF" stopOpacity="0.5" />
          <stop offset="100%" stopColor="#25E2AF" stopOpacity="0" />
        </linearGradient>
      </defs>
      <g stroke="url(#wave-fade)" fill="none" strokeWidth="1.2">
        <path d="M -50 620 C 150 560, 250 700, 450 640 S 750 520, 900 600" />
        <path d="M -50 700 C 180 640, 260 780, 470 710 S 760 600, 900 680" />
        <path d="M -50 780 C 160 730, 300 850, 480 790 S 780 690, 900 760" />
        <path d="M -50 850 C 200 810, 320 920, 500 870 S 800 780, 900 840" />
      </g>
      <g fill="#25E2AF">
        {[
          [80, 640, 0.5],
          [180, 600, 0.35],
          [320, 660, 0.6],
          [420, 610, 0.3],
          [540, 700, 0.45],
          [640, 650, 0.35],
          [140, 730, 0.4],
          [300, 760, 0.3],
          [460, 800, 0.5],
          [600, 760, 0.3],
          [720, 720, 0.4],
          [220, 850, 0.35],
          [380, 890, 0.45],
          [540, 850, 0.3],
          [680, 880, 0.35],
        ].map(([cx, cy, o], i) => (
          <circle key={i} cx={cx} cy={cy} r="2.5" opacity={o} />
        ))}
      </g>
    </svg>
  );
}

function BrandShape() {
  return (
    <svg
      className="absolute -right-16 -bottom-24 h-[420px] w-[420px] opacity-[0.07]"
      viewBox="0 0 200 180"
      aria-hidden="true"
    >
      <g stroke="#25E2AF" strokeWidth="3" fill="none" strokeLinejoin="round">
        <path d="M20 40 L90 40 L70 65 L140 65" />
        <path d="M10 80 L80 80 L60 105 L130 105" />
        <path d="M0 120 L70 120 L50 145 L120 145" />
      </g>
    </svg>
  );
}

export function LoginBrandPanel() {
  return (
    <div className="relative hidden w-[44%] max-w-md shrink-0 flex-col justify-between overflow-hidden bg-[#121212] px-12 py-10 lg:flex xl:w-[40%]">
      <BrandTexture />
      <BrandShape />

      <div className="relative z-10 flex items-center gap-2.5">
        <Image
          src="/assets/featcode-symbol.png"
          alt=""
          width={26}
          height={23}
          className="h-[22px] w-auto object-contain"
        />
        <span className="text-lg leading-none font-semibold tracking-tight text-white">
          Featcode
        </span>
      </div>

      <div className="relative z-10 max-w-sm">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-[#25E2AF]/25 bg-[#25E2AF]/10 px-2.5 py-1 text-[11px] font-semibold tracking-wide text-[#25E2AF] uppercase">
          <span className="size-1.5 rounded-full bg-[#25E2AF]" />
          Internal tool
        </span>
        <h2 className="mt-5 text-[28px] leading-[1.2] font-medium text-white">
          The recruiting platform built for Featcode.
        </h2>
        <p className="mt-4 text-sm leading-relaxed text-[#ADB1BA]">
          An internal featTalent product developed to help Featcode find,
          evaluate, and hire high-performing talent, faster.
        </p>
      </div>

      <p className="relative z-10 text-xs text-[#6B7277]">
        © {new Date().getFullYear()} Featcode Technology
      </p>
    </div>
  );
}
