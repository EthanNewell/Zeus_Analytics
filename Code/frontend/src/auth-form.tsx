import { renderToStaticMarkup } from "react-dom/server"
import { ArrowRight, Eye, EyeOff, CircleAlert } from "lucide-react"
import { Button } from "./components/ui/button"
import { Input } from "./components/ui/input"
import { Field, FieldError, FieldGroup, FieldLabel } from "./components/ui/field"
import { Card, CardContent, CardDescription, CardHeader } from "./components/ui/card"
import { Alert, AlertDescription } from "./components/ui/alert"

function CredentialField({ password = false }: { password?: boolean }) {
  const name = password ? "password" : "username"
  const id = "id_" + name
  return <Field className="credential">
    <FieldLabel htmlFor={id}>{password ? "Пароль" : "Логин"}</FieldLabel>
    <div className="input-wrap">
      <Input type={password ? "password" : "text"} id={id} name={name} required
        aria-invalid={`{% if form.${name}.errors %}true{% else %}false{% endif %}` as "true"}
        aria-describedby={id + "_error"}
        maxLength={password ? undefined : 150} autoComplete={password ? "current-password" : "username"}
        defaultValue={password ? undefined : "__BOUND_USERNAME__"} />
      {password && <Button type="button" variant="ghost" size="icon" id="toggle-password" hidden
        aria-label="Показать пароль" aria-controls={id} aria-pressed="false"><Eye/><EyeOff/></Button>}
    </div>
    <div id={id + "_error"}>{`{% if form.${name}.errors %}`}<FieldError>{`{{ form.${name}.errors }}`}</FieldError>{"{% endif %}"}</div>
  </Field>
}

function AuthCard() {
  return <Card className="auth-card">
    <CardHeader><h1>Вход в систему</h1>
      <CardDescription>Используйте учётную запись, выданную администратором.</CardDescription>
    </CardHeader>
    <CardContent>
      {"{% if form.non_field_errors %}"}
      <Alert variant="destructive" className="form-alert"><CircleAlert/><AlertDescription>{"{{ form.non_field_errors }}"}</AlertDescription></Alert>
      {"{% endif %}"}
      <FieldGroup><CredentialField/><CredentialField password/></FieldGroup>
      <Button className="submit-button" type="submit">Войти<ArrowRight aria-hidden="true"/></Button>
    </CardContent>
  </Card>
}
export function renderForm() {
  return renderToStaticMarkup(<AuthCard/>).replace("__BOUND_USERNAME__", "{{ form.username.value|default_if_none:'' }}")
}
