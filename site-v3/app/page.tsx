import Nav from "@/components/Nav";
import HeroSection from "@/components/HeroSection";
import StackShowcase from "@/components/StackShowcase";
import Mission3D from "@/components/Mission3D";
import ExplodedView from "@/components/ExplodedView";
import GateDemo from "@/components/GateDemo";
import {
  Mission,
  Detector,
  Hardware,
  Safety,
  Proof,
  Footer,
} from "@/components/Sections";

export default function Home() {
  return (
    <main>
      <Nav />
      <HeroSection />
      <Mission />
      <Mission3D />
      <Detector />
      <GateDemo />
      <Hardware />
      <StackShowcase />
      <ExplodedView />
      <Safety />
      <Proof />
      <Footer />
    </main>
  );
}
