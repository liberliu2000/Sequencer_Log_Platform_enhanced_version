import { LogPlatformConsole } from "@/components/log-platform-console";

export default function Home() {
  return (
    <div className="min-h-screen bg-[var(--background)]">
      <div className="mx-auto w-full max-w-[1600px] px-4 py-6 md:px-6 lg:px-8 lg:py-8">
        <LogPlatformConsole />
      </div>
    </div>
  );
}
