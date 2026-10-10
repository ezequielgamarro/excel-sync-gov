import { createClient } from "@supabase/supabase-js";

// Valores por defecto = proyecto `centroestadistica` (la clave `anon` es pública
// y está protegida por RLS). Se pueden sobrescribir con las variables VITE_*.
const url = import.meta.env.VITE_SUPABASE_URL || "https://fkrabqcxhdyaxfuhqvmp.supabase.co";
const key =
  import.meta.env.VITE_SUPABASE_ANON_KEY ||
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZrcmFicWN4aGR5YXhmdWhxdm1wIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTE2MzI0MDIsImV4cCI6MjEwNzIwODQwMn0.giEpdAH965_AwFowUgRC_FFeIlVYMKRZf4lw6ntbJwk";

export const supabase = createClient(url, key);
