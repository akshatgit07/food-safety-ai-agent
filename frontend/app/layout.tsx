import { ReactNode } from 'react';

import './globals.css';

export const metadata = {
  title: 'Guiltless AI · Nutrition Copilot',
  description: 'Explain food labels, compare products, optimize a shopping bag, and plan meals.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0 }}>{children}</body>
    </html>
  );
}
