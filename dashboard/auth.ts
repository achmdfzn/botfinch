import NextAuth from "next-auth";
import Discord from "next-auth/providers/discord";

declare module "next-auth" {
  interface Session {
    accessToken?: string;
    discordId?: string;
  }
}

// signIn/signOut tidak dipakai di mana pun (AuthButtons memakai
// next-auth/react) — hanya handlers + auth yang diekspor.
export const { handlers, auth } = NextAuth({
  trustHost: true,
  providers: [
    Discord({
      // Auth.js v5 membaca AUTH_DISCORD_ID/AUTH_DISCORD_SECRET dari env;
      // kita oper eksplisit agar nama env di .env.example tetap berlaku.
      clientId: process.env.DISCORD_CLIENT_ID,
      clientSecret: process.env.DISCORD_CLIENT_SECRET,
      authorization: { params: { scope: "identify guilds" } },
      // Discord kini mengirim ?iss=https://discord.com di callback;
      // tanpa ini Auth.js menolak dengan "unexpected iss".
      issuer: "https://discord.com",
    }),
  ],
  callbacks: {
    async jwt({ token, account }) {
      if (account?.access_token) token.accessToken = account.access_token;
      if (account?.providerAccountId) token.discordId = account.providerAccountId;
      return token;
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken as string | undefined;
      session.discordId = token.discordId as string | undefined;
      return session;
    },
  },
});
