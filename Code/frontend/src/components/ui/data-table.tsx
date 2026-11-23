import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./table"

export function DataTable<T, V>({ columns, data }: { columns: ColumnDef<T, V>[]; data: T[] }) {
  const table = useReactTable({ columns, data, getCoreRowModel: getCoreRowModel() })
  return <Table>
    <TableHeader>{table.getHeaderGroups().map(group => <TableRow key={group.id}>
      {group.headers.map(header => <TableHead key={header.id} colSpan={header.colSpan}>
        {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
      </TableHead>)}
    </TableRow>)}</TableHeader>
    <TableBody>{table.getRowModel().rows.map(row => <TableRow key={row.id}>
      {row.getVisibleCells().map(cell => <TableCell key={cell.id}>
        {flexRender(cell.column.columnDef.cell, cell.getContext())}
      </TableCell>)}
    </TableRow>)}
    {data.length === 0 && <TableRow><TableCell colSpan={columns.length} className="text-center">Нет данных</TableCell></TableRow>}
    </TableBody>
  </Table>
}
