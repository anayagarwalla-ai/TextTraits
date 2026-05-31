import React, {useState} from "react";
import {
  Button,
  Divider,
  Flex,
  Heading,
  Input,
  Text,
  TextArea,
  hubspot,
} from "@hubspot/ui-extensions";

const TEXTTRAITS_BASE_URL = "__TEXTTRAITS_PUBLIC_BASE_URL__";

hubspot.extend(({context}) => <TextTraitsEmailFitCard context={context} />);

function TextTraitsEmailFitCard({context}) {
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const updateSubject = (value) => setSubject(typeof value === "string" ? value : value?.target?.value || value?.value || "");
  const updateBody = (value) => setBody(typeof value === "string" ? value : value?.target?.value || value?.value || "");

  const analyze = async () => {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const response = await hubspot.fetch(`${TEXTTRAITS_BASE_URL}/v1/integrations/hubspot/crm-card/analyze-email`, {
        method: "POST",
        body: {
          workspace_id: `hubspot_${context?.portal?.id || context?.portalId || "workspace"}`,
          inputFields: {
            subject,
            body,
            audience: "HubSpot CRM record",
            intent: "CRM outreach review",
          },
        },
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.error || "TextTraits analysis failed.");
      }
      setResult(payload);
    } catch (requestError) {
      setError(requestError.message || "TextTraits is unavailable.");
    } finally {
      setLoading(false);
    }
  };

  const output = result?.outputFields || {};
  return (
    <Flex direction="column" gap="medium">
      <Heading>TextTraits email fit</Heading>
      <Text>Paste an existing email draft to score it before routing. TextTraits returns decision-support fields only.</Text>
      <Input label="Subject" name="subject" value={subject} onInput={updateSubject} placeholder="Renewal workflow follow-up" />
      <TextArea label="Body" name="body" value={body} onInput={updateBody} placeholder="Paste an existing draft email body." />
      <Button disabled={loading || !subject || !body} onClick={analyze}>
        {loading ? "Analyzing" : "Analyze draft"}
      </Button>
      {error ? <Text>{error}</Text> : null}
      {result ? (
        <Flex direction="column" gap="small">
          <Divider />
          <Text>Score: {output.texttraits_score}</Text>
          <Text>Gate: {output.texttraits_gate}</Text>
          <Text>Route: {output.texttraits_route}</Text>
          <Text>Request ID: {output.texttraits_request_id}</Text>
        </Flex>
      ) : null}
    </Flex>
  );
}
