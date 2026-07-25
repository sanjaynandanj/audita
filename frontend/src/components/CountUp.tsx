import { useEffect, useRef, useState } from "react";

export default function CountUp({ value, prefix = "₹" }: { value: string | number; prefix?: string }) {
  const target = typeof value === "string" ? parseFloat(value) : value;
  const [display, setDisplay] = useState(0);
  const prev = useRef(0);

  useEffect(() => {
    if (!isFinite(target)) return;
    const from = prev.current;
    prev.current = target;
    const dur = 800;
    const t0 = performance.now();
    let raf: number;
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      setDisplay(from + (target - from) * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target]);

  return (
    <span className="tabular-nums">
      {prefix}
      {display.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
    </span>
  );
}
