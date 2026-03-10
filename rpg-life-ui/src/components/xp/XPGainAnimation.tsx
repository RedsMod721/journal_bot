import { motion, AnimatePresence } from "framer-motion";
import { useEffect, useState } from "react";
import { Zap } from "lucide-react";

interface XPGainAnimationProps {
  amount: number;
  onComplete?: () => void;
}

export function XPGainAnimation({ amount, onComplete }: XPGainAnimationProps) {
  const [isVisible, setIsVisible] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsVisible(false);
      onComplete?.();
    }, 2000);

    return () => clearTimeout(timer);
  }, [onComplete]);

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ scale: 0, y: 0 }}
          animate={{
            scale: [0, 1.2, 1],
            y: [-50, 0],
          }}
          exit={{ scale: 0, opacity: 0 }}
          transition={{
            duration: 0.5,
            ease: "easeOut",
          }}
          className="fixed top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 z-50"
        >
          <div className="flex flex-col items-center gap-4 p-8 rounded-2xl bg-accent/20 backdrop-blur-lg border-2 border-accent shadow-2xl shadow-accent/50">
            <motion.div
              animate={{
                rotate: [0, -10, 10, -10, 0],
                scale: [1, 1.1, 1, 1.1, 1],
              }}
              transition={{
                duration: 0.5,
                repeat: 2,
              }}
            >
              <Zap className="w-16 h-16 text-accent" />
            </motion.div>
            <div className="text-center">
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ delay: 0.2 }}
                className="text-5xl font-display font-bold text-accent"
              >
                +{amount.toLocaleString()}
              </motion.div>
              <div className="text-xl font-medium text-accent mt-2">
                XP Gained!
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
