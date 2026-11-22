import * as React from "react"
import { ru } from "date-fns/locale"
import { CalendarIcon } from "lucide-react"
import { Button } from "./button"
import { Calendar } from "./calendar"
import { Popover, PopoverContent, PopoverTrigger } from "./popover"

type Props = { value?: Date; onChange: (date?: Date) => void; disabled?: boolean }
export function DatePicker({ value, onChange, disabled }: Props) {
  const [open, setOpen] = React.useState(false)
  return <Popover open={open} onOpenChange={setOpen}>
    <PopoverTrigger asChild><Button variant="outline" disabled={disabled}>
      <CalendarIcon />{value ? value.toLocaleDateString("ru-RU") : "Выберите дату"}
    </Button></PopoverTrigger>
    <PopoverContent className="w-auto p-0" align="start">
      <Calendar mode="single" locale={ru} selected={value} defaultMonth={value}
        onSelect={date => { onChange(date); setOpen(false) }} />
    </PopoverContent>
  </Popover>
}
