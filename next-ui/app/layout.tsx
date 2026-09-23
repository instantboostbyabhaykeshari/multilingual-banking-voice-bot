import "./globals.css";

export const metadata = { title: "Native Voice Bot", description: "Assessment call monitor" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
