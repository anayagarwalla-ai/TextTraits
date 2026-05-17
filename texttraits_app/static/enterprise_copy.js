(function () {
  function compactPhrase(value, limit = 5) {
    const clean = String(value || "").replace(/\s+/g, " ").trim();
    const parts = clean.split(" ").filter(Boolean);
    return parts.length > limit ? parts.slice(0, limit).join(" ") : clean;
  }

  function subjectLines(context) {
    const pain = compactPhrase(String(context.pain || "").split(" and ")[0], 4);
    return [
      `Two accounts worth coaching this week`,
      `Before ${compactPhrase(context.trigger, 4)} gets noisy`,
      `A cleaner manager handoff`,
      `${context.company} x {{company}}`,
      `Quick read on ${pain}`,
    ];
  }

  function ctaText(context) {
    if (context.goal === "Book call") return "Worth a quick 15-minute fit call?";
    if (context.goal === "Revive lead") return "Should I send a tighter version of the idea?";
    if (context.goal === "Follow up") return "Is this still worth keeping on the radar?";
    if (context.goal === "Expand account") return "Would it help to map this against the next team?";
    return "Want the short event follow-up brief?";
  }

  function buildEmailVariant(context, variant, options = {}) {
    const learned = options.learned || [];
    const feedback = options.feedback || {};
    const preferShort = Number(feedback.tooLong || 0) > Number(feedback.better || 0);
    const preferSpecific = Number(feedback.tooVague || 0) > 0;
    const learnedLine = learned.includes("Proof before product")
      ? "I would lead with one proof point before getting into product detail."
      : "I would keep this about the manager's next review, not a broad platform pitch.";
    const tonePrefix = variant === "A"
      ? `The buyer's language points to one practical problem: ${context.pain}.`
      : variant === "B"
        ? `This does not sound like they need more dashboards. It sounds like ${compactPhrase(context.trigger, 5)} is making the next coaching move harder to choose.`
        : `For ${context.role}, the useful hook is a calmer handoff before the next account review.`;
    const proof = variant === "A" ? context.proof : variant === "B" ? context.caseStudy : context.competitor;
    const body = variant === "A"
      ? `${tonePrefix}

If that is the pressure right now, I would keep the email anchored to one job: help managers see which two accounts deserve coaching before the next review.

${context.company} helps ${context.segment} teams turn ${context.trigger} into a short list of named accounts, the reason each one matters, and the exact rep note a manager should review. The proof point to anchor on is ${proof}.${preferSpecific ? ` The first test could focus on ${context.icp}.` : ""}

${preferShort ? ctaText(context) : `${learnedLine}\n\n${ctaText(context)}`}`
      : variant === "B"
        ? `${tonePrefix}

The useful angle is simple: one list managers can trust before the team meeting, with the account, the coaching reason, and the next rep note in the same place.

I would test the ${context.trigger} angle and use ${proof} as the proof point.${preferSpecific ? ` Keep the first conversation focused on ${context.icp}.` : ""}

${ctaText(context)}`
        : `${tonePrefix}

I would frame this as a calmer way to prepare for review: fewer manual check-ins, cleaner account notes, and less guessing about where managers should spend time this week.

${context.company} can position ${context.offer} around that weekly rhythm, with ${proof} as the concrete reason to take a look.

${ctaText(context)}`;
    return `Subject: ${subjectLines(context)[variant === "A" ? 0 : variant === "B" ? 1 : 2]}

Hi {{first_name}},

${body}`;
  }

  function buildSequence(context) {
    return [
      ["Day 1", "Initial email", `Subject: ${subjectLines(context)[0]}\n\nHi {{first_name}},\n\nI noticed the team is focused on ${context.pain}. If the goal is earlier visibility without another reporting loop, I had a short idea tied to ${context.trigger}.\n\n${ctaText(context)}`],
      ["Day 3", "LinkedIn touch", `Saw the same theme around ${compactPhrase(context.pain, 5)}. Happy to send the two-bullet version if useful.`],
      ["Day 6", "Proof follow-up", `One proof point that may be relevant: ${context.proof}. The useful shift is usually fewer manual check-ins and earlier coaching moments.`],
      ["Day 10", "Breakup note", `Should I close the loop, or would a short summary on ${context.trigger} be useful later?`],
    ];
  }

  function inboxReply(thread, context) {
    const firstName = context.firstName || "{{first_name}}";
    if (thread.type === "interested") return `Hi ${firstName}, glad that is the key question. The short version: you can evaluate this without a heavy migration. Worth a focused 15-minute fit call next week?`;
    if (thread.type === "objection") return `Hi ${firstName}, that makes sense. I would not pitch this as another dashboard. The useful angle is cleaner manager visibility before forecast review. Want me to send a two-bullet example?`;
    if (thread.type === "referral") return `Hi ${firstName}, thanks for pointing me in the right direction. Would it be easier if I sent two bullets you can forward to the RevOps lead?`;
    if (thread.type === "not-now") return `Hi ${firstName}, understood. I can step back until planning wraps. If helpful, I can send a short summary now so it is easy to revisit later.`;
    if (thread.type === "unsubscribe") return `Hi ${firstName}, understood. I will remove you from this sequence.`;
    return `Hi ${firstName}, thanks for the context. ${thread.next}`;
  }

  window.TextTraitsEnterpriseCopy = {
    compactPhrase,
    subjectLines,
    ctaText,
    buildEmailVariant,
    buildSequence,
    inboxReply,
  };
})();
