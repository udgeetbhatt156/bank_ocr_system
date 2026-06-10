import Link from "next/link";

export default function CreditsPage() {
    return (
        <div>
            <h1 className="mx-auto mt-10 text-2xl font-semibold">Credits Page</h1>

            <Link href="/transactions" className="w-30 px-4 py-3 mx-auto mt-5 block text-sm text-white rounded-full bg-[#0061FE] hover:bg-blue-600 transition-colors font-medium">Back</Link>
        </div>
    );
}
