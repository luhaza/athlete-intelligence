"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-4 text-center">
      <p className="text-gray-500 text-sm">
        {error.message.startsWith("API error")
          ? "Could not reach the API. Is the backend running?"
          : "Something went wrong."}
      </p>
      <button
        onClick={reset}
        className="px-4 py-2 text-sm rounded-lg border border-gray-200 hover:bg-gray-50 transition-colors"
      >
        Try again
      </button>
    </div>
  );
}
