-- Global Macro Desk: AI view (Gemini) twice a day. Run once in Supabase -> SQL Editor.
-- 02:55 UTC = 8:25 am IST (before India opens), 13:25 UTC = 6:55 pm IST (before the US opens).
do $$ begin perform cron.unschedule('gm-ai-brief'); exception when others then null; end $$;
select cron.schedule('gm-ai-brief', '55 2,13 * * *',
  $$select public.dispatch_repo_workflow('global-macro-desk', 'ai-brief.yml')$$);
