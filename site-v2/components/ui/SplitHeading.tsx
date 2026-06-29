'use client'

import { useRef } from "react";
import { motion, useInView, useReducedMotion } from "framer-motion";

type Props = {
  text: string;
  as?: "h1" | "h2" | "h3";
  className?: string;
  stagger?: number;
};

// Heading that splits into words and springs each in on scroll entry.
export default function SplitHeading({
  text,
  as = "h2",
  className,
  stagger = 0.04,
}: Props) {
  const ref = useRef<HTMLHeadingElement>(null);
  const inView = useInView(ref, { once: true, margin: "-50px" });
  const reduce = useReducedMotion();
  const words = text.split(" ");

  const Tag = motion[as] as typeof motion.h2;

  return (
    <Tag ref={ref} className={className}>
      {words.map((word, i) => (
        <motion.span
          key={`${word}-${i}`}
          className="inline-block whitespace-pre"
          initial={reduce ? false : { y: 30, opacity: 0 }}
          animate={
            reduce ? undefined : inView ? { y: 0, opacity: 1 } : undefined
          }
          transition={{
            type: "spring",
            stiffness: 100,
            damping: 20,
            delay: i * stagger,
          }}
        >
          {i < words.length - 1 ? word + " " : word}
        </motion.span>
      ))}
    </Tag>
  );
}
