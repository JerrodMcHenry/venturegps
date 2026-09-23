// VentureGPS Increment 16 -- always-visible, unmissable prototype labeling. This banner is the first thing on
// the page (before the hero) so no one -- reviewer or, if this URL were ever shared, a stray visitor -- can
// scroll past it without knowing this is a design prototype, not the live VentureGPS product.
export default function PrototypeBanner() {
  return (
    <div className="border-b border-dashed border-warning/40 bg-warning-soft px-4 py-2.5 text-center text-sm font-medium text-warning sm:px-6">
      Design prototype &mdash; Increment 16 &middot; Not the production Discover page &middot; Sample data throughout
    </div>
  );
}
