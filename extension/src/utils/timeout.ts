// Wraps a promise so it rejects after `ms` if it hasn't settled — used for
// cross-context round-trips (e.g. service worker <-> offscreen document) that
// could otherwise hang indefinitely if the other side crashes mid-operation.
// requirement.md: "Do not leave the extension indefinitely in a loading state."
export function withTimeout<T>(promise: Promise<T>, ms: number, message: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(message)), ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (err) => {
        clearTimeout(timer);
        reject(err);
      },
    );
  });
}
