import {useCallback, useMemo, useRef, useState} from "react";


export function useFormState(initialValues) {
  const [values, setValues] = useState(initialValues);
  const fieldNames = useRef(Object.keys(initialValues));
  const setField = useCallback((name, nextValue) => {
    setValues((current) => {
      const resolved = typeof nextValue === "function" ? nextValue(current[name]) : nextValue;
      return Object.is(current[name], resolved) ? current : {...current, [name]: resolved};
    });
  }, []);
  const handlers = useMemo(
    () => Object.fromEntries(fieldNames.current.map((name) => [name, (value) => setField(name, value)])),
    [setField],
  );
  return {values, handlers, setField};
}
